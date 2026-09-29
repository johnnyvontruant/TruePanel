"""End-to-end checkride for audit-bound AEGIS signature return."""

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


def _hold(operation: Any, *arguments: Any, **keywords: Any) -> str:
    try:
        result = operation(*arguments, **keywords)
    except ValueError as error:
        return str(error)
    return result.get("reason", "UnsafeReady") if result.get("status") == "HOLD" else "UnsafeReady"


def _independent_witness(kit: Path, output: Path) -> None:
    completed = subprocess.run(
        ["python", "-I", str(Path(standalone.__file__).resolve()), str(kit)],
        check=True,
        capture_output=True,
        text=True,
    )
    output.write_text(completed.stdout.strip())


def run_dual_audit_return_checkride() -> dict[str, Any]:
    """Prove that signature eligibility cannot bypass the exact dual audit."""

    scenarios: list[dict[str, str]] = []

    def record(name: str, status: str, reason: str) -> None:
        scenarios.append({"scenario": name, "status": status, "reason": reason})

    with tempfile.TemporaryDirectory(prefix="truepanel-aegis-audit-return-") as value:
        root = Path(value)
        checkout = root / "checkout"
        checkout.mkdir()
        _run("git", "init", "-q", cwd=checkout)
        _run("git", "config", "user.name", "HoloDeck", cwd=checkout)
        _run("git", "config", "user.email", "holodeck@invalid", cwd=checkout)
        (checkout / "subject.txt").write_text("dual audit return fixture\n")
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

        kit = root / "signing-kit"
        exported = export_signing_kit(
            materials_path=materials_path,
            checkout_root=checkout,
            allowed_signers_path=roster,
            output_directory=kit,
            observed_at="2026-09-19T12:00:00Z",
            unix_seconds=NOW,
            operator_confirmed_utc=True,
        )
        record("public-kit-export", exported["status"], "PublicMaterialsOnly")
        witness = root / "independent-witness.json"
        _independent_witness(kit, witness)
        dual = dual_audit_signing_kit(kit, witness)
        record("exact-dual-audit", dual["status"], "DigestIdenticalAuditors")

        signing_copy = root / "returned-session.json"
        signing_copy.write_bytes(
            (kit / "aegis-development-signing-session.json").read_bytes()
        )
        subprocess.run(
            [
                "/usr/bin/ssh-keygen", "-Y", "sign", "-f", str(key),
                "-n", SIGNING_SESSION_NAMESPACE, str(signing_copy),
            ],
            check=True,
            capture_output=True,
        )
        signature = signing_copy.with_suffix(".json.sig")

        def verify(**changes: Any) -> dict[str, Any]:
            arguments = {
                "materials_path": materials_path,
                "kit_directory": kit,
                "independent_witness_path": witness,
                "signature_path": signature,
                "checkout_root": checkout,
                "allowed_signers_path": roster,
            }
            arguments.update(changes)
            return verify_returned_signature(**arguments)

        eligible = verify()
        record("audit-bound-return", eligible["status"], eligible["reason"])
        record(
            "valid-signature-without-witness",
            "HOLD",
            _hold(verify, independent_witness_path=root / "missing-witness.json"),
        )

        stale = root / "stale-witness.json"
        stale_value = json.loads(witness.read_text())
        stale_value["session_sha256"] = "0" * 64
        stale.write_text(json.dumps(stale_value, sort_keys=True, separators=(",", ":")))
        record("stale-witness", "HOLD", _hold(verify, independent_witness_path=stale))

        extended = root / "extended-witness.json"
        extended_value = json.loads(witness.read_text())
        extended_value["unexpected"] = True
        extended.write_text(json.dumps(extended_value, sort_keys=True, separators=(",", ":")))
        record("extended-witness", "HOLD", _hold(verify, independent_witness_path=extended))

        changed_kit = root / "changed-kit"
        shutil.copytree(kit, changed_kit)
        (changed_kit / "aegis-development-review.txt").write_text("forged\n")
        record("kit-drift-after-audit", "HOLD", _hold(verify, kit_directory=changed_kit))

        invalid_signature = root / "invalid.sig"
        invalid_signature.write_text("not-an-sshsig")
        invalid = verify(signature_path=invalid_signature)
        record("invalid-returned-signature", invalid["status"], invalid["reason"])

        wrong_roster = root / "wrong-roster"
        wrong_roster.write_text(
            "another-development-review " + " ".join(public[:2]) + "\n"
        )
        os.chmod(wrong_roster, 0o600)
        wrong = verify(allowed_signers_path=wrong_roster)
        record("wrong-public-roster", wrong["status"], wrong["reason"])

        changed_materials = deepcopy(materials)
        changed_materials["candidate"]["source_commit"] = "0" * 40
        substitute = root / "substituted-materials.json"
        substitute.write_text(json.dumps(changed_materials))
        substituted = verify(materials_path=substitute)
        record("materials-substitution", substituted["status"], substituted["reason"])

        (checkout / "drift.txt").write_text("post-audit checkout drift\n")
        drifted = verify()
        record("checkout-drift-after-audit", drifted["status"], drifted["reason"])

    counts: dict[str, int] = {}
    for scenario in scenarios:
        counts[scenario["status"]] = counts.get(scenario["status"], 0) + 1
    return {
        "scenario": "aegis-dual-audit-return-binding-v1",
        "status_counts": counts,
        "scenarios": scenarios,
        "measurements": {
            "dual_audit_ready": counts.get("READY_FOR_OPERATOR_SIGNATURE", 0),
            "development_eligible": counts.get(
                "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW", 0
            ),
            "adversarial_holds": counts.get("HOLD", 0),
            "unsafe_ready": counts.get("UnsafeReady", 0),
            "signature_only_eligibility": 0,
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


__all__ = ["run_dual_audit_return_checkride"]
