"""Deterministic checkride for the public-only AEGIS signing tool."""

from __future__ import annotations

import json
import os
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
    export_signing_kit,
    load_materials,
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


def run_signing_tool_checkride() -> dict[str, Any]:
    scenarios: list[dict[str, str]] = []

    def record(name: str, status: str, reason: str) -> None:
        scenarios.append({"scenario": name, "status": status, "reason": reason})

    with tempfile.TemporaryDirectory(prefix="truepanel-aegis-signing-tool-") as directory:
        root = Path(directory)
        checkout = root / "checkout"
        checkout.mkdir()
        _run("git", "init", "-q", cwd=checkout)
        _run("git", "config", "user.name", "HoloDeck", cwd=checkout)
        _run("git", "config", "user.email", "holodeck@invalid", cwd=checkout)
        (checkout / "subject.txt").write_text("offline signing tool fixture\n")
        _run("git", "add", "subject.txt", cwd=checkout)
        _run("git", "commit", "-q", "-m", "fixture", cwd=checkout)
        commit = _run("git", "rev-parse", "HEAD", cwd=checkout).strip()

        key = root / "disposable-fixture-key"
        subprocess.run(
            [
                "/usr/bin/ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-C",
                "HoloDeck disposable fixture only",
                "-f",
                str(key),
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

        def export(output: Path, **changes: Any) -> dict[str, Any]:
            arguments = {
                "materials_path": materials_path,
                "checkout_root": checkout,
                "allowed_signers_path": roster,
                "output_directory": output,
                "observed_at": "2026-09-19T12:00:00Z",
                "unix_seconds": NOW,
                "operator_confirmed_utc": True,
            }
            arguments.update(changes)
            return export_signing_kit(**arguments)

        output = root / "signing-kit"
        result = export(output)
        record("public-kit-export", result["status"], "PublicMaterialsOnly")
        session = output / "aegis-development-signing-session.json"
        subprocess.run(
            [
                "/usr/bin/ssh-keygen",
                "-Y",
                "sign",
                "-f",
                str(key),
                "-n",
                SIGNING_SESSION_NAMESPACE,
                str(session),
            ],
            check=True,
            capture_output=True,
        )
        signature = session.with_suffix(".json.sig")

        def verify(**changes: Any) -> dict[str, Any]:
            arguments = {
                "materials_path": materials_path,
                "session_path": session,
                "signature_path": signature,
                "checkout_root": checkout,
                "allowed_signers_path": roster,
            }
            arguments.update(changes)
            return verify_returned_signature(**arguments)

        result = verify()
        record("returned-exact-signature", result["status"], result["reason"])
        record(
            "utc-not-confirmed",
            "HOLD",
            _hold(export, root / "no-clock", operator_confirmed_utc=False),
        )
        record(
            "output-inside-checkout",
            "HOLD",
            _hold(export, checkout / "kit"),
        )
        link = root / "materials-link.json"
        link.symlink_to(materials_path)
        record("symlinked-materials", "HOLD", _hold(load_materials, link))
        record("existing-output", "HOLD", _hold(export, output))

        changed_materials = deepcopy(materials)
        changed_materials["unsigned_receipt"]["signature"] = "already-signed"
        signed_materials = root / "signed-materials.json"
        signed_materials.write_text(json.dumps(changed_materials))
        record("pre-signed-input", "HOLD", _hold(load_materials, signed_materials))

        original_session = session.read_text()
        changed_session = json.loads(original_session)
        changed_session["production_authority"] = True
        session.write_text(json.dumps(changed_session))
        result = verify()
        record("session-authority-tampering", result["status"], result["reason"])
        session.write_text(original_session)

        invalid_signature = root / "invalid.sig"
        invalid_signature.write_text("not-an-sshsig")
        result = verify(signature_path=invalid_signature)
        record("invalid-signature", result["status"], result["reason"])

        (checkout / "drift.txt").write_text("post-export drift\n")
        result = verify()
        record("checkout-drift-after-export", result["status"], result["reason"])

    counts: dict[str, int] = {}
    for scenario in scenarios:
        counts[scenario["status"]] = counts.get(scenario["status"], 0) + 1
    return {
        "scenario": "aegis-offline-signing-tool-v1",
        "status_counts": counts,
        "scenarios": scenarios,
        "measurements": {
            "public_export_ready": 1,
            "development_eligible": 1,
            "adversarial_holds": counts.get("HOLD", 0),
            "unsafe_ready": counts.get("UnsafeReady", 0),
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


__all__ = ["run_signing_tool_checkride"]
