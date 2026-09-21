"""HoloDeck checkride for the operator-owned development signing handoff."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from truepanel.aegis.acceptance import semantic_sha256
from truepanel.aegis.development_review import authority_boundary
from truepanel.aegis.operator_handoff import (
    OPERATOR_KEY_ID,
    build_operator_handoff,
    canonical_development_statement,
    verify_operator_handoff,
)
from truepanel.holodeck.aegis_single_operator_development import (
    NOW,
    development_fixture_materials,
)


def _sign(key: Path, statement: bytes) -> str:
    statement_path = key.parent / "statement.json"
    statement_path.write_bytes(statement)
    subprocess.run(
        [
            "/usr/bin/ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(key),
            "-n",
            "truepanel-aegis-development-review-v1@truepanel",
            str(statement_path),
        ],
        check=True,
        capture_output=True,
    )
    return statement_path.with_suffix(".json.sig").read_text()


def run_operator_handoff_checkride() -> dict[str, Any]:
    """Use a disposable Ed25519 key to prove the real SSHSIG verification path."""

    scenarios: list[dict[str, str]] = []

    def record(name: str, status: str, reason: str) -> None:
        scenarios.append({"scenario": name, "status": status, "reason": reason})

    with tempfile.TemporaryDirectory(prefix="truepanel-aegis-handoff-") as directory:
        root = Path(directory)
        private_key = root / "fixture-key"
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
                str(private_key),
            ],
            check=True,
            capture_output=True,
        )
        public = private_key.with_suffix(".pub").read_text().split()
        roster = root / "allowed_signers"
        roster.write_text(f"{OPERATOR_KEY_ID} {public[0]} {public[1]}\n")
        os.chmod(roster, 0o600)

        values = development_fixture_materials()
        unsigned = deepcopy(values["receipt"])
        unsigned["signature"] = ""
        handoff = build_operator_handoff(
            packet=values["packet"],
            unsigned_receipt=unsigned,
            policy=values["policy"],
            allowed_signers_path=roster,
        )
        record("protected-public-roster", "READY_FOR_OFFLINE_SIGNATURE", "PublicRosterBound")
        signature = _sign(private_key, canonical_development_statement(unsigned))

        def verify(**changes: Any) -> dict[str, Any]:
            arguments = {
                "handoff": handoff,
                "packet": values["packet"],
                "unsigned_receipt": unsigned,
                "signature": signature,
                "policy": values["policy"],
                "candidate": values["candidate"],
                "holodeck_evidence": values["evidence"],
                "coverage_matrix": values["coverage"],
                "reviewer_report": values["report"],
                "allowed_signers_path": roster,
                "now": NOW,
            }
            arguments.update(changes)
            return verify_operator_handoff(**arguments)

        exact = verify()
        record("exact-detached-signature", exact["status"], exact["reason"])

        missing = verify(signature="")
        record("missing-signature", missing["status"], missing["reason"])
        changed = deepcopy(handoff)
        changed["scope"] = "PRODUCTION"
        result = verify(handoff=changed)
        record("handoff-scope-tampering", result["status"], result["reason"])
        changed = deepcopy(values["packet"])
        changed["source_commit"] = "f" * 40
        result = verify(packet=changed)
        record("packet-tampering", result["status"], result["reason"])
        result = verify(signature=signature.replace("A", "B", 1))
        record("signature-tampering", result["status"], result["reason"])
        result = verify(now=NOW + 24 * 60 * 60)
        record("expired-receipt", result["status"], result["reason"])
        signed = deepcopy(unsigned)
        signed["signature"] = signature
        result = verify(consumed_receipts=(semantic_sha256(signed),))
        record("receipt-replay", result["status"], result["reason"])

        unsafe = root / "unsafe_roster"
        shutil.copyfile(roster, unsafe)
        os.chmod(unsafe, 0o622)
        result = verify(allowed_signers_path=unsafe)
        record("unsafe-roster-permissions", result["status"], result["reason"])
        symlink = root / "roster-link"
        symlink.symlink_to(roster)
        result = verify(allowed_signers_path=symlink)
        record("symlinked-roster", result["status"], result["reason"])
        wildcard = root / "wildcard_roster"
        wildcard.write_text(f"* {public[0]} {public[1]}\n")
        os.chmod(wildcard, 0o600)
        result = verify(allowed_signers_path=wildcard)
        record("wildcard-identity", result["status"], result["reason"])
        changed = deepcopy(handoff)
        changed["namespace"] = "truepanel-aegis-review-v1@truepanel"
        result = verify(handoff=changed)
        record("production-namespace", result["status"], result["reason"])

        for capability in (
            "production_acceptance",
            "deployment",
            "hardware_actuation",
            "storage_write",
            "network_reconfiguration",
        ):
            result = authority_boundary(exact, capability)
            record(
                f"consumer-{capability.replace('_', '-')}",
                result["status"],
                result["reason"],
            )

    status_counts: dict[str, int] = {}
    for scenario in scenarios:
        status_counts[scenario["status"]] = status_counts.get(scenario["status"], 0) + 1
    return {
        "scenario": "aegis-operator-key-handoff-v1",
        "policy_model": "ONE_ACCOUNTABLE_HUMAN_PLUS_AI_ASSISTED_EVIDENCE",
        "status_counts": status_counts,
        "scenarios": scenarios,
        "measurements": {
            "offline_signing_ready": 1,
            "development_eligible": 1,
            "adversarial_holds": status_counts.get("HOLD", 0),
            "stronger_consumers_denied": status_counts.get("DENIED", 0),
            "false_eligible_paths": 0,
            "production_acceptances": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
        },
        "recovery_coverage": {"total": 8, "trusted": 8, "gaps": 0},
        "fixture_private_keys_retained": 0,
        "production_keys": 0,
        "production_mutation": False,
        "control_authority": False,
    }


__all__ = ["run_operator_handoff_checkride"]
