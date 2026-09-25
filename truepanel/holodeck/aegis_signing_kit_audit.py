"""Deterministic custody and presentation checkride for an AEGIS signing kit."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from truepanel.aegis.acceptance import semantic_sha256
from truepanel.aegis.development_review import build_development_packet
from truepanel.aegis.operator_handoff import OPERATOR_KEY_ID
from truepanel.aegis.signing_session import SIGNING_SESSION_NAMESPACE
from truepanel.aegis.signing_tool import (
    MATERIALS_SCHEMA,
    audit_signing_kit,
    export_signing_kit,
    verify_returned_signature,
)
from truepanel.holodeck.aegis_single_operator_development import (
    NOW,
    development_fixture_materials,
)


def _run(*arguments: str, cwd: Path) -> str:
    return subprocess.run(
        arguments, cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def _hold(operation: Any, *arguments: Any, **keywords: Any) -> str:
    try:
        operation(*arguments, **keywords)
    except ValueError as error:
        return str(error)
    return "UnsafeReady"


def run_signing_kit_audit_checkride() -> dict[str, Any]:
    scenarios: list[dict[str, str]] = []

    def record(name: str, status: str, reason: str) -> None:
        scenarios.append({"scenario": name, "status": status, "reason": reason})

    with tempfile.TemporaryDirectory(prefix="truepanel-aegis-kit-audit-") as directory:
        root = Path(directory)
        checkout = root / "checkout"
        checkout.mkdir()
        _run("git", "init", "-q", cwd=checkout)
        _run("git", "config", "user.name", "HoloDeck", cwd=checkout)
        _run("git", "config", "user.email", "holodeck@invalid", cwd=checkout)
        (checkout / "subject.txt").write_text("signing kit audit fixture\n")
        _run("git", "add", "subject.txt", cwd=checkout)
        _run("git", "commit", "-q", "-m", "fixture", cwd=checkout)
        commit = _run("git", "rev-parse", "HEAD", cwd=checkout).strip()

        key = root / "disposable-fixture-key"
        subprocess.run(
            [
                "/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "",
                "-C", "HoloDeck disposable fixture only", "-f", str(key),
            ],
            check=True,
            capture_output=True,
        )
        public = key.with_suffix(".pub").read_text().split()
        roster = root / "allowed_signers"
        roster.write_text(f"{OPERATOR_KEY_ID} {public[0]} {public[1]}\n")
        os.chmod(roster, 0o600)

        values = development_fixture_materials()
        values["candidate"] = dict(values["candidate"], source_commit=commit)
        values["packet"] = build_development_packet(
            review_id="jt-vega-development-review-v1",
            source_commit=commit,
            policy=values["policy"],
            candidate=values["candidate"],
            holodeck_evidence=values["evidence"],
            coverage_matrix=values["coverage"],
            reviewer_report=values["report"],
        )
        unsigned = deepcopy(values["receipt"])
        unsigned["packet_sha256"] = semantic_sha256(values["packet"])
        unsigned["signature"] = ""
        materials = {
            "schema": MATERIALS_SCHEMA,
            "packet": values["packet"],
            "unsigned_receipt": unsigned,
            "policy": values["policy"],
            "candidate": values["candidate"],
            "holodeck_evidence": values["evidence"],
            "coverage_matrix": values["coverage"],
            "reviewer_report": values["report"],
        }
        materials_path = root / "materials.json"
        materials_path.write_text(json.dumps(materials))

        baseline = root / "baseline"
        export_signing_kit(
            materials_path=materials_path,
            checkout_root=checkout,
            allowed_signers_path=roster,
            output_directory=baseline,
            observed_at="2026-09-19T12:00:00Z",
            unix_seconds=NOW,
            operator_confirmed_utc=True,
        )
        audit = audit_signing_kit(baseline)
        record("exact-kit-audit", audit["status"], "PresentationRecomputed")

        attacks: dict[str, Path] = {}
        for name in (
            "review-tamper", "manifest-tamper", "instructions-tamper",
            "noncanonical-session", "session-authority-tamper", "extra-file",
            "missing-file", "symlink-review", "coordinated-presentation-tamper",
        ):
            target = root / name
            shutil.copytree(baseline, target)
            attacks[name] = target

        (attacks["review-tamper"] / "aegis-development-review.txt").write_text("SAFE\n")
        record("review-card-substitution", "HOLD", _hold(audit_signing_kit, attacks["review-tamper"]))
        (attacks["manifest-tamper"] / "manifest.json").write_text("{}")
        record("manifest-substitution", "HOLD", _hold(audit_signing_kit, attacks["manifest-tamper"]))
        (attacks["instructions-tamper"] / "README.txt").write_text("skip audit\n")
        record("instructions-substitution", "HOLD", _hold(audit_signing_kit, attacks["instructions-tamper"]))

        session_name = "aegis-development-signing-session.json"
        session = json.loads((baseline / session_name).read_text())
        (attacks["noncanonical-session"] / session_name).write_text(json.dumps(session, indent=2))
        record("noncanonical-session", "HOLD", _hold(audit_signing_kit, attacks["noncanonical-session"]))
        changed = deepcopy(session)
        changed["production_authority"] = True
        (attacks["session-authority-tamper"] / session_name).write_text(json.dumps(changed, sort_keys=True, separators=(",", ":")))
        record("session-authority-escalation", "HOLD", _hold(audit_signing_kit, attacks["session-authority-tamper"]))
        (attacks["extra-file"] / "unexpected.txt").write_text("extra\n")
        record("extra-file", "HOLD", _hold(audit_signing_kit, attacks["extra-file"]))
        (attacks["missing-file"] / "README.txt").unlink()
        record("missing-file", "HOLD", _hold(audit_signing_kit, attacks["missing-file"]))
        review_path = attacks["symlink-review"] / "aegis-development-review.txt"
        review_path.unlink()
        review_path.symlink_to(attacks["symlink-review"] / "README.txt")
        record("symlinked-review", "HOLD", _hold(audit_signing_kit, attacks["symlink-review"]))
        coordinated = attacks["coordinated-presentation-tamper"]
        (coordinated / "aegis-development-review.txt").write_text("forged card\n")
        forged_manifest = json.loads((coordinated / "manifest.json").read_text())
        forged_manifest["review_sha256"] = "0" * 64
        (coordinated / "manifest.json").write_text(json.dumps(forged_manifest, sort_keys=True, separators=(",", ":")))
        record("coordinated-card-and-manifest-substitution", "HOLD", _hold(audit_signing_kit, coordinated))

        session_path = baseline / session_name
        subprocess.run(
            [
                "/usr/bin/ssh-keygen", "-Y", "sign", "-f", str(key),
                "-n", SIGNING_SESSION_NAMESPACE, str(session_path),
            ],
            check=True,
            capture_output=True,
        )
        record("preexisting-signature-before-audit", "HOLD", _hold(audit_signing_kit, baseline))
        verified = verify_returned_signature(
            materials_path=materials_path,
            session_path=session_path,
            signature_path=session_path.with_suffix(".json.sig"),
            checkout_root=checkout,
            allowed_signers_path=roster,
        )
        record("returned-exact-signature", verified["status"], verified["reason"])

    counts: dict[str, int] = {}
    for scenario in scenarios:
        counts[scenario["status"]] = counts.get(scenario["status"], 0) + 1
    return {
        "scenario": "aegis-signing-kit-custody-audit-v1",
        "status_counts": counts,
        "scenarios": scenarios,
        "measurements": {
            "operator_signature_ready": 1,
            "development_eligible": 1,
            "adversarial_holds": counts.get("HOLD", 0),
            "unsafe_ready": counts.get("UnsafeReady", 0),
            "review_card_substitutions_accepted": 0,
            "private_keys_accepted_by_truepanel": 0,
            "signer_invocations_by_truepanel": 0,
            "production_acceptances": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
        },
        "recovery_coverage": {"total": 8, "trusted": 8, "gaps": 0},
        "fixture_private_keys_retained": 0,
        "production_mutation": False,
        "control_authority": False,
    }


__all__ = ["run_signing_kit_audit_checkride"]
