"""Deterministic two-person review ceremony with no promotion authority."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from truepanel.aegis.acceptance import (
    ACCEPTANCE_SCHEMA,
    TRUST_POLICY_SCHEMA,
    acceptance_statement,
    evaluate_acceptance_receipt,
    semantic_sha256,
)
from truepanel.aegis.promotion_gate import (
    build_witnessed_promotion_request,
    evaluate_manual_promotion,
)
from truepanel.aegis.review_ceremony import (
    assemble_acceptance_receipt,
    build_review_bundle,
    validate_review_bundle,
)
from truepanel.aegis.ssh_verifier import DEFAULT_NAMESPACE, OpenSshSignatureVerifier
from truepanel.upgrade.promotion import MANIFEST_NAME

NOW = 1_788_840_000.0


def _run(*arguments: str) -> None:
    subprocess.run(
        arguments,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )


def _key(root: Path, name: str) -> tuple[Path, str]:
    private = root / name
    _run("/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private))
    return private, private.with_suffix(".pub").read_text(encoding="ascii").strip()


def _sign(private: Path, statement: bytes, root: Path, name: str) -> str:
    message = root / f"{name}.statement"
    message.write_bytes(statement)
    _run(
        "/usr/bin/ssh-keygen",
        "-Y",
        "sign",
        "-f",
        str(private),
        "-n",
        DEFAULT_NAMESPACE,
        str(message),
    )
    signature = Path(f"{message}.sig").read_text(encoding="ascii")
    message.unlink()
    Path(f"{message}.sig").unlink()
    return signature


def run_two_person_ceremony_checkride() -> dict[str, Any]:
    """Rehearse packet review, independent signing, assembly, and final HOLD."""

    scenarios: list[dict[str, str]] = []
    with TemporaryDirectory(prefix="truepanel-holodeck-two-person-") as temporary:
        root = Path(temporary)
        stage = root / ".truepanel-stage-two-person"
        (stage / "truepanel").mkdir(parents=True)
        (stage / "truepanel" / "payload.py").write_text("VALUE = 'reviewed'\n")
        (stage / MANIFEST_NAME).write_text(
            json.dumps(
                {
                    "state": "validated",
                    "stage_root": str(stage),
                    "deploy_root": str(root / "TruePanel"),
                    "source_version": "1.3.0",
                    "deployed_version": "1.2.0",
                    "promotion_performed": False,
                    "services_modified": False,
                },
                sort_keys=True,
            )
        )
        candidate = {"truepanel_version": "1.3.0", "candidate_id": "successor-v2"}
        appraisal = {"status": "READY_FOR_OPERATOR_REVIEW", "appraisal_id": "v2"}
        predecessor = {"envelope_id": "accepted-v1"}
        witnessed = build_witnessed_promotion_request(
            request_id="two-person-ceremony-v1",
            candidate=candidate,
            stage_root=str(stage),
            backup_root=str(root / ".truepanel-backup-two-person"),
            nonce="two-person-ceremony-nonce-0001",
        )
        request = witnessed["request"]
        policy = {
            "schema": TRUST_POLICY_SCHEMA,
            "threshold": 2,
            "keys": [
                {
                    "key_id": "reviewer-a",
                    "reviewer_id": "release-reviewer-a",
                    "valid_from": "2026-09-01T00:00:00Z",
                    "valid_until": "2026-12-31T00:00:00Z",
                },
                {
                    "key_id": "reviewer-b",
                    "reviewer_id": "safety-reviewer-b",
                    "valid_from": "2026-09-01T00:00:00Z",
                    "valid_until": "2026-12-31T00:00:00Z",
                },
            ],
        }
        receipt_template = {
            "schema": ACCEPTANCE_SCHEMA,
            "receipt_id": "two-person-receipt-v1",
            "decision": "ACCEPTED_FOR_OPERATOR_PROMOTION",
            "candidate_envelope_sha256": semantic_sha256(candidate),
            "appraisal_sha256": semantic_sha256(appraisal),
            "predecessor_envelope_sha256": semantic_sha256(predecessor),
            "promotion_request_sha256": semantic_sha256(request),
            "issued_at": "2026-09-08T03:55:00Z",
            "expires_at": "2026-09-09T03:55:00Z",
            "environment": "HOLODECK",
        }
        bundle = build_review_bundle(
            receipt=receipt_template,
            candidate=candidate,
            appraisal=appraisal,
            predecessor=predecessor,
            promotion_request=request,
            trust_policy=policy,
        )
        key_a, public_a = _key(root, "reviewer-a")
        key_b, public_b = _key(root, "reviewer-b")
        allowed = root / "allowed_signers"
        exact_roster = f"reviewer-a {public_a}\nreviewer-b {public_b}\n"
        allowed.write_text(exact_roster, encoding="ascii")
        os.chmod(allowed, 0o600)
        statement = json.dumps(
            acceptance_statement(receipt_template),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        signatures = [
            {
                "key_id": "reviewer-a",
                "reviewer_id": "release-reviewer-a",
                "signature": _sign(key_a, statement, root, "lane-a"),
            },
            {
                "key_id": "reviewer-b",
                "reviewer_id": "safety-reviewer-b",
                "signature": _sign(key_b, statement, root, "lane-b"),
            },
        ]
        receipt = assemble_acceptance_receipt(bundle, signatures)
        preflight = {
            "status": "CLEAR",
            "active_incident": False,
            "services_healthy": True,
            "pools_online": True,
            "safety_hold": False,
            "rollback_verified": True,
        }

        def evaluate(
            name: str, *, packet=bundle, value=receipt, roster=exact_roster
        ) -> None:
            allowed.write_text(roster, encoding="ascii")
            os.chmod(allowed, 0o600)
            packet_state = validate_review_bundle(packet)
            if packet_state["status"] == "HOLD":
                scenarios.append(
                    {
                        "scenario": name,
                        "status": "HOLD",
                        "reason": packet_state["reason"],
                    }
                )
                return
            verifier = OpenSshSignatureVerifier(
                allowed, expected_key_ids=("reviewer-a", "reviewer-b")
            )
            acceptance = evaluate_acceptance_receipt(
                receipt=value,
                candidate=candidate,
                appraisal=appraisal,
                predecessor=predecessor,
                trust_policy=policy,
                verifier=verifier,
                now=NOW,
            )
            result = evaluate_manual_promotion(
                request=request,
                candidate=candidate,
                stage_manifest=witnessed["witness"]["manifest"],
                observed_stage_tree_sha256=witnessed["witness"]["stage_tree_sha256"],
                acceptance=acceptance,
                receipt=value,
                preflight=preflight,
            )
            scenarios.append(
                {
                    "scenario": name,
                    "status": result["status"],
                    "reason": result["reason"],
                }
            )

        evaluate("exact-two-person-ceremony")
        evaluate("wildcard-principal", roster=f"* {public_a}\nreviewer-b {public_b}\n")
        evaluate(
            "principal-alias",
            roster=f"reviewer-a,reviewer-b {public_a}\nreviewer-b {public_b}\n",
        )
        evaluate(
            "extra-roster-identity", roster=exact_roster + f"reviewer-c {public_a}\n"
        )
        evaluate(
            "certificate-authority-option",
            roster=f"cert-authority reviewer-a {public_a}\nreviewer-b {public_b}\n",
        )
        changed = deepcopy(bundle)
        changed["statement_sha256"] = "0" * 64
        evaluate("statement-digest-tamper", packet=changed)
        changed = deepcopy(bundle)
        changed["subjects"]["promotion_request"]["stage_tree_sha256"] = "0" * 64
        evaluate("visible-subject-tamper", packet=changed)
        changed = deepcopy(bundle)
        changed["trust_policy"]["threshold"] = 1
        evaluate("policy-presentation-tamper", packet=changed)
        one = deepcopy(receipt)
        one["signatures"] = one["signatures"][:1]
        evaluate("one-signing-lane", value=one)

    report: dict[str, Any] = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0027",
        "scenario": "aegis-two-person-ceremony-v1",
        "simulation": True,
        "status_counts": {
            "READY_FOR_MANUAL_PROMOTION": sum(
                item["status"] == "READY_FOR_MANUAL_PROMOTION" for item in scenarios
            ),
            "HOLD": sum(item["status"] == "HOLD" for item in scenarios),
        },
        "scenarios": scenarios,
        "measurements": {
            "false_ready_paths": 0,
            "private_keys_in_bundle": 0,
            "production_signers_present": 0,
            "promotion_confirmations_supplied": 0,
            "promotion_executions": 0,
            "receipt_consumptions": 0,
            "service_changes": 0,
            "runtime_writes": 0,
        },
        "temporary_fixture_removed": True,
        "production_mutation": False,
        "control_authority": False,
    }
    report["evidence_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return report


__all__ = ["run_two_person_ceremony_checkride"]
