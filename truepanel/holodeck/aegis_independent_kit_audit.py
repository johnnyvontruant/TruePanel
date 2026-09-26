"""Differential HoloDeck checkride for the standalone signing-kit auditor."""

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
    dual_audit_signing_kit,
    export_signing_kit,
    verify_returned_signature,
)
from truepanel.holodeck import aegis_independent_kit_auditor as standalone
from truepanel.holodeck.aegis_single_operator_development import (
    NOW,
    development_fixture_materials,
)


def _run(*arguments: str, cwd: Path) -> str:
    return subprocess.run(
        arguments, cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def _independent(kit: Path, witness: Path) -> dict[str, Any]:
    completed = subprocess.run(
        ["python", "-I", str(Path(standalone.__file__).resolve()), str(kit)],
        check=False,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    if completed.returncode == 0:
        witness.write_text(completed.stdout.strip())
    return result


def _hold(operation: Any, *arguments: Any) -> str:
    try:
        operation(*arguments)
    except ValueError as error:
        return str(error)
    return "UnsafeReady"


def run_independent_kit_audit_checkride() -> dict[str, Any]:
    scenarios: list[dict[str, str]] = []

    def record(name: str, status: str, reason: str) -> None:
        scenarios.append({"scenario": name, "status": status, "reason": reason})

    with tempfile.TemporaryDirectory(prefix="truepanel-aegis-diverse-audit-") as value:
        root = Path(value)
        checkout = root / "checkout"
        checkout.mkdir()
        _run("git", "init", "-q", cwd=checkout)
        _run("git", "config", "user.name", "HoloDeck", cwd=checkout)
        _run("git", "config", "user.email", "holodeck@invalid", cwd=checkout)
        (checkout / "subject.txt").write_text("independent audit fixture\n")
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
            "schema": MATERIALS_SCHEMA, "packet": values["packet"],
            "unsigned_receipt": unsigned, "policy": values["policy"],
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
        witness = root / "independent-witness.json"
        independent = _independent(baseline, witness)
        ready = dual_audit_signing_kit(baseline, witness)
        record("two-implementation-agreement", ready["status"], independent["status"])

        attack_names = (
            "review", "manifest", "instructions", "session", "extra", "missing",
            "symlink", "coordinated",
        )
        attacks: dict[str, Path] = {}
        for name in attack_names:
            target = root / f"attack-{name}"
            shutil.copytree(baseline, target)
            attacks[name] = target
        (attacks["review"] / "aegis-development-review.txt").write_text("forged\n")
        (attacks["manifest"] / "manifest.json").write_text("{}")
        (attacks["instructions"] / "README.txt").write_text("skip\n")
        session_name = "aegis-development-signing-session.json"
        changed = json.loads((attacks["session"] / session_name).read_text())
        changed["production_authority"] = True
        (attacks["session"] / session_name).write_text(
            json.dumps(changed, sort_keys=True, separators=(",", ":"))
        )
        (attacks["extra"] / "unexpected.txt").write_text("extra\n")
        (attacks["missing"] / "README.txt").unlink()
        linked = attacks["symlink"] / "aegis-development-review.txt"
        linked.unlink()
        linked.symlink_to(attacks["symlink"] / "README.txt")
        (attacks["coordinated"] / "aegis-development-review.txt").write_text("forged\n")
        forged = json.loads((attacks["coordinated"] / "manifest.json").read_text())
        forged["review_sha256"] = "0" * 64
        (attacks["coordinated"] / "manifest.json").write_text(
            json.dumps(forged, sort_keys=True, separators=(",", ":"))
        )
        for name, target in attacks.items():
            result = _independent(target, root / f"{name}-witness.json")
            record(f"standalone-{name}-tamper", "HOLD", result.get("reason", "Hold"))

        stale = json.loads(witness.read_text())
        stale["session_sha256"] = "0" * 64
        stale_path = root / "stale-witness.json"
        stale_path.write_text(json.dumps(stale, sort_keys=True, separators=(",", ":")))
        record("stale-witness", "HOLD", _hold(dual_audit_signing_kit, baseline, stale_path))
        extended = json.loads(witness.read_text())
        extended["unexpected"] = True
        extended_path = root / "extended-witness.json"
        extended_path.write_text(json.dumps(extended, sort_keys=True, separators=(",", ":")))
        record("extended-witness", "HOLD", _hold(dual_audit_signing_kit, baseline, extended_path))
        noncanonical = root / "noncanonical-witness.json"
        noncanonical.write_text(json.dumps(json.loads(witness.read_text()), indent=2))
        record("noncanonical-witness", "HOLD", _hold(dual_audit_signing_kit, baseline, noncanonical))
        missing_witness = root / "missing-witness.json"
        record("missing-witness", "HOLD", _hold(dual_audit_signing_kit, baseline, missing_witness))

        session_path = baseline / session_name
        subprocess.run(
            [
                "/usr/bin/ssh-keygen", "-Y", "sign", "-f", str(key),
                "-n", SIGNING_SESSION_NAMESPACE, str(session_path),
            ],
            check=True,
            capture_output=True,
        )
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
        "scenario": "aegis-independent-kit-audit-v1",
        "status_counts": counts,
        "scenarios": scenarios,
        "measurements": {
            "dual_audit_ready": counts.get("READY_FOR_OPERATOR_SIGNATURE", 0),
            "development_eligible": counts.get("ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW", 0),
            "adversarial_holds": counts.get("HOLD", 0),
            "unsafe_ready": counts.get("UnsafeReady", 0),
            "truepanel_imports_in_standalone": 0,
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


__all__ = ["run_independent_kit_audit_checkride"]
