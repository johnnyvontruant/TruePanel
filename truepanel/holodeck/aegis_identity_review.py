"""Deterministic two-person checkride for identity-coverage review."""

from __future__ import annotations

import json
import os
import subprocess
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from truepanel.aegis.acceptance import TRUST_POLICY_SCHEMA
from truepanel.aegis.coverage import coverage_matrix
from truepanel.aegis.coverage_appraisal import (
    appraise_identity_coverage_candidate,
    semantic_sha256,
)
from truepanel.aegis.coverage_review import (
    REVIEW_DECISION,
    REVIEW_RECEIPT_SCHEMA,
    build_identity_review_packet,
    coverage_review_statement,
    evaluate_identity_review_receipt,
)
from truepanel.aegis.identity_coverage import (
    build_identity_coverage_candidate,
    rehearse_identity_coverage_contract,
)
from truepanel.aegis.rehearsal import rehearse_recovery_paths
from truepanel.aegis.ssh_verifier import DEFAULT_NAMESPACE, OpenSshSignatureVerifier

NOW = datetime(2026, 9, 17, 4, 30, tzinfo=UTC).timestamp()


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
    signature_path = Path(f"{message}.sig")
    signature = signature_path.read_text(encoding="ascii")
    message.unlink()
    signature_path.unlink()
    return signature


def run_identity_review_rehearsal() -> dict[str, Any]:
    """Rehearse quorum and binding without any production trust material."""

    accepted = coverage_matrix(rehearse_recovery_paths())
    candidate = build_identity_coverage_candidate(
        accepted, rehearse_identity_coverage_contract()
    )
    appraisal = appraise_identity_coverage_candidate(
        accepted_matrix=accepted, candidate=candidate
    )
    packet = build_identity_review_packet(
        accepted_matrix=accepted,
        candidate=candidate,
        appraisal=appraisal,
    )
    scenarios: list[dict[str, str]] = []

    with TemporaryDirectory(prefix="truepanel-holodeck-identity-review-") as temporary:
        root = Path(temporary)
        key_a, public_a = _key(root, "reviewer-a")
        key_b, public_b = _key(root, "reviewer-b")
        allowed = root / "allowed_signers"
        roster = f"reviewer-a {public_a}\nreviewer-b {public_b}\n"
        allowed.write_text(roster, encoding="ascii")
        os.chmod(allowed, 0o600)
        policy = {
            "schema": TRUST_POLICY_SCHEMA,
            "threshold": 2,
            "keys": [
                {
                    "key_id": "reviewer-a",
                    "reviewer_id": "reliability-reviewer-a",
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
        receipt = {
            "schema": REVIEW_RECEIPT_SCHEMA,
            "receipt_id": "identity-coverage-review-checkride-v1",
            "decision": REVIEW_DECISION,
            "packet_sha256": semantic_sha256(packet),
            "issued_at": "2026-09-17T04:00:00Z",
            "expires_at": "2026-09-18T04:00:00Z",
            "environment": "HOLODECK",
            "signatures": [],
        }
        statement = json.dumps(
            coverage_review_statement(receipt),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        signatures = [
            {
                "key_id": "reviewer-a",
                "reviewer_id": "reliability-reviewer-a",
                "signature": _sign(key_a, statement, root, "lane-a"),
            },
            {
                "key_id": "reviewer-b",
                "reviewer_id": "safety-reviewer-b",
                "signature": _sign(key_b, statement, root, "lane-b"),
            },
        ]
        receipt["signatures"] = signatures

        def evaluate(
            name: str,
            expected: str,
            *,
            packet_value: dict[str, Any] | None = None,
            receipt_value: dict[str, Any] | None = None,
            candidate_value: dict[str, Any] | None = None,
            policy_value: dict[str, Any] | None = None,
            namespace: str = DEFAULT_NAMESPACE,
            mode: int = 0o600,
        ) -> None:
            allowed.write_text(roster, encoding="ascii")
            os.chmod(allowed, mode)
            verifier = OpenSshSignatureVerifier(
                allowed,
                namespace=namespace,
                expected_key_ids=("reviewer-a", "reviewer-b"),
            )
            result = evaluate_identity_review_receipt(
                packet=packet_value or packet,
                receipt=receipt_value or receipt,
                accepted_matrix=accepted,
                candidate=candidate_value or candidate,
                appraisal=appraisal,
                trust_policy=policy_value or policy,
                verifier=verifier,
                now=NOW,
            )
            scenarios.append(
                {
                    "name": name,
                    "expected": expected,
                    "actual": result["status"],
                    "reason": result["reason"],
                }
            )

        evaluate("two-independent-reviewers", "ELIGIBLE_FOR_SUCCESSOR_ENVELOPE_DRAFT")

        one_signature = deepcopy(receipt)
        one_signature["signatures"] = one_signature["signatures"][:1]
        evaluate("one-reviewer", "HOLD", receipt_value=one_signature)

        duplicate_signature = deepcopy(receipt)
        duplicate_signature["signatures"] = [signatures[0], signatures[0]]
        evaluate("duplicate-reviewer", "HOLD", receipt_value=duplicate_signature)

        expired = deepcopy(receipt)
        expired["expires_at"] = "2026-09-17T04:15:00Z"
        evaluate("expired-review", "HOLD", receipt_value=expired)

        packet_tamper = deepcopy(packet)
        packet_tamper["unreviewed_extension"] = True
        evaluate("packet-extension", "HOLD", packet_value=packet_tamper)

        candidate_tamper = deepcopy(candidate)
        candidate_tamper["accepted"] = True
        evaluate("candidate-tamper", "HOLD", candidate_value=candidate_tamper)

        evaluate("namespace-mismatch", "HOLD", namespace="other-purpose")
        evaluate("unsafe-roster-permissions", "HOLD", mode=0o622)

        duplicate_policy = deepcopy(policy)
        duplicate_policy["keys"][1]["reviewer_id"] = "reliability-reviewer-a"
        evaluate("duplicate-policy-identity", "HOLD", policy_value=duplicate_policy)

    false_outcomes = sum(item["actual"] != item["expected"] for item in scenarios)
    return {
        "schema": "truepanel.holodeck-aegis-identity-review/v1",
        "experiment_id": "TP-EXP-0031",
        "simulation": True,
        "field_validated": False,
        "result": "PASS" if false_outcomes == 0 else "FAIL",
        "measurements": {
            "scenarios": len(scenarios),
            "eligible": sum(
                item["actual"] == "ELIGIBLE_FOR_SUCCESSOR_ENVELOPE_DRAFT"
                for item in scenarios
            ),
            "holds": sum(item["actual"] == "HOLD" for item in scenarios),
            "false_outcomes": false_outcomes,
            "false_eligible": sum(
                item["expected"] == "HOLD"
                and item["actual"] == "ELIGIBLE_FOR_SUCCESSOR_ENVELOPE_DRAFT"
                for item in scenarios
            ),
            "candidate_acceptances": 0,
            "successor_envelopes_created": 0,
            "runtime_writes": 0,
            "production_writes": 0,
        },
        "scenarios": scenarios,
        "safety": {
            "private_keys": "disposable-holodeck-only",
            "production_keys": 0,
            "live_provider_access": False,
            "hardware_actions": 0,
            "recovery_actions": 0,
            "automatic_acceptance": False,
            "control_authority": False,
        },
    }


__all__ = ["run_identity_review_rehearsal"]
