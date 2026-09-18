"""Deterministic checkride for the identity-coverage envelope draft boundary."""

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
from truepanel.aegis.assurance import load_assurance_envelope
from truepanel.aegis.coverage import coverage_matrix
from truepanel.aegis.coverage_appraisal import (
    appraise_identity_coverage_candidate,
    semantic_sha256,
)
from truepanel.aegis.coverage_envelope import prepare_coverage_successor_draft
from truepanel.aegis.coverage_review import (
    REVIEW_DECISION,
    REVIEW_RECEIPT_SCHEMA,
    build_identity_review_packet,
    coverage_review_statement,
    evaluate_identity_review_receipt,
    prepare_identity_review_handoff,
)
from truepanel.aegis.identity_coverage import (
    build_identity_coverage_candidate,
    rehearse_identity_coverage_contract,
)
from truepanel.aegis.passive_runtime import BoundedTrueNASQueryCache
from truepanel.aegis.platform_witness import (
    bind_platform_witness,
    issue_platform_witness,
)
from truepanel.aegis.policy import DEFAULT_CORRELATION_POLICY
from truepanel.aegis.rehearsal import rehearse_recovery_paths
from truepanel.aegis.requalification import evaluate_successor_envelope
from truepanel.aegis.ssh_verifier import DEFAULT_NAMESPACE, OpenSshSignatureVerifier

NOW = datetime(2026, 9, 18, 4, 30, tzinfo=UTC).timestamp()


class _Client:
    def call(self, _method: str, *_arguments: Any) -> str:
        return "TrueNAS-SCALE-25.10.5"


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


def run_coverage_envelope_rehearsal() -> dict[str, Any]:
    """Prove reviewed draft construction and fail-closed mutations."""

    root = Path(__file__).resolve().parents[1]
    accepted_envelope = load_assurance_envelope()
    accepted_matrix = coverage_matrix(rehearse_recovery_paths())
    candidate = build_identity_coverage_candidate(
        accepted_matrix, rehearse_identity_coverage_contract()
    )
    appraisal = appraise_identity_coverage_candidate(
        accepted_matrix=accepted_matrix, candidate=candidate
    )
    packet = build_identity_review_packet(
        accepted_matrix=accepted_matrix,
        candidate=candidate,
        appraisal=appraisal,
    )

    with TemporaryDirectory(prefix="truepanel-holodeck-coverage-envelope-") as temporary:
        temporary_root = Path(temporary)
        key_a, public_a = _key(temporary_root, "reviewer-a")
        key_b, public_b = _key(temporary_root, "reviewer-b")
        allowed = temporary_root / "allowed_signers"
        allowed.write_text(
            f"reviewer-a {public_a}\nreviewer-b {public_b}\n", encoding="ascii"
        )
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
            "receipt_id": "coverage-envelope-draft-checkride-v1",
            "decision": REVIEW_DECISION,
            "packet_sha256": semantic_sha256(packet),
            "issued_at": "2026-09-18T04:00:00Z",
            "expires_at": "2026-09-19T04:00:00Z",
            "environment": "HOLODECK",
            "signatures": [],
        }
        statement = json.dumps(
            coverage_review_statement(receipt),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        receipt["signatures"] = [
            {
                "key_id": "reviewer-a",
                "reviewer_id": "reliability-reviewer-a",
                "signature": _sign(key_a, statement, temporary_root, "lane-a"),
            },
            {
                "key_id": "reviewer-b",
                "reviewer_id": "safety-reviewer-b",
                "signature": _sign(key_b, statement, temporary_root, "lane-b"),
            },
        ]
        review = evaluate_identity_review_receipt(
            packet=packet,
            receipt=receipt,
            accepted_matrix=accepted_matrix,
            candidate=candidate,
            appraisal=appraisal,
            trust_policy=policy,
            verifier=OpenSshSignatureVerifier(
                allowed, expected_key_ids=("reviewer-a", "reviewer-b")
            ),
            now=NOW,
        )

    draft_result = prepare_coverage_successor_draft(
        accepted_envelope=accepted_envelope,
        accepted_matrix=accepted_matrix,
        candidate_matrix=candidate,
        appraisal=appraisal,
        review_result=review,
        issued_at="2026-09-18T04:05:00Z",
        expires_at="2026-12-15T04:05:00Z",
        package_root=root,
    )
    draft = draft_result["draft"]
    witness = issue_platform_witness(
        BoundedTrueNASQueryCache(_Client()), clock=lambda: NOW
    )
    payload = bind_platform_witness({"system": {}}, witness)
    scenarios: list[dict[str, str]] = []

    def appraise(name: str, value: dict[str, Any], expected: str) -> None:
        result = evaluate_successor_envelope(
            accepted=accepted_envelope,
            candidate=value,
            payload=payload,
            coverage_matrix=candidate,
            correlation_policy=DEFAULT_CORRELATION_POLICY.describe(),
            now=NOW,
            package_root=root,
        )
        actual = (
            "READY_FOR_INDEPENDENT_ENVELOPE_REVIEW"
            if result["status"] == "READY_FOR_OPERATOR_REVIEW"
            else "HOLD"
        )
        scenarios.append(
            {
                "name": name,
                "expected": expected,
                "actual": actual,
                "reason": result["reason"],
            }
        )

    appraise("reviewed-exact-draft", draft, "READY_FOR_INDEPENDENT_ENVELOPE_REVIEW")

    unsigned = prepare_coverage_successor_draft(
        accepted_envelope=accepted_envelope,
        accepted_matrix=accepted_matrix,
        candidate_matrix=candidate,
        appraisal=appraisal,
        review_result=prepare_identity_review_handoff(
            accepted_matrix=accepted_matrix,
            candidate=candidate,
            appraisal=appraisal,
        ),
        issued_at="2026-09-18T04:05:00Z",
        expires_at="2026-12-15T04:05:00Z",
        package_root=root,
    )
    scenarios.append(
        {
            "name": "unsigned-review-handoff",
            "expected": "HOLD",
            "actual": unsigned["status"],
            "reason": unsigned["reason"],
        }
    )

    spoofed_review = deepcopy(review)
    spoofed_review["valid_reviewer_count"] = 1
    spoofed = prepare_coverage_successor_draft(
        accepted_envelope=accepted_envelope,
        accepted_matrix=accepted_matrix,
        candidate_matrix=candidate,
        appraisal=appraisal,
        review_result=spoofed_review,
        issued_at="2026-09-18T04:05:00Z",
        expires_at="2026-12-15T04:05:00Z",
        package_root=root,
    )
    scenarios.append(
        {
            "name": "review-count-spoof",
            "expected": "HOLD",
            "actual": spoofed["status"],
            "reason": spoofed["reason"],
        }
    )

    changed_candidate = deepcopy(candidate)
    changed_candidate["accepted"] = True
    candidate_hold = prepare_coverage_successor_draft(
        accepted_envelope=accepted_envelope,
        accepted_matrix=accepted_matrix,
        candidate_matrix=changed_candidate,
        appraisal=appraisal,
        review_result=review,
        issued_at="2026-09-18T04:05:00Z",
        expires_at="2026-12-15T04:05:00Z",
        package_root=root,
    )
    scenarios.append(
        {
            "name": "candidate-after-review-tamper",
            "expected": "HOLD",
            "actual": candidate_hold["status"],
            "reason": candidate_hold["reason"],
        }
    )

    changed_appraisal = deepcopy(appraisal)
    changed_appraisal["status"] = "HOLD"
    appraisal_hold = prepare_coverage_successor_draft(
        accepted_envelope=accepted_envelope,
        accepted_matrix=accepted_matrix,
        candidate_matrix=candidate,
        appraisal=changed_appraisal,
        review_result=review,
        issued_at="2026-09-18T04:05:00Z",
        expires_at="2026-12-15T04:05:00Z",
        package_root=root,
    )
    scenarios.append(
        {
            "name": "appraisal-after-review-tamper",
            "expected": "HOLD",
            "actual": appraisal_hold["status"],
            "reason": appraisal_hold["reason"],
        }
    )

    coverage_drift = deepcopy(draft)
    coverage_drift["coverage_sha256"] = "0" * 64
    appraise("draft-coverage-drift", coverage_drift, "HOLD")

    subject_drift = deepcopy(draft)
    subject_drift["subjects"][0]["sha256"] = "0" * 64
    appraise("draft-subject-drift", subject_drift, "HOLD")

    automatic = deepcopy(draft)
    automatic["automatic_acceptance"] = True
    appraise("draft-automatic-acceptance", automatic, "HOLD")

    expired = deepcopy(draft)
    expired["expires_at"] = "2026-09-18T04:15:00Z"
    appraise("draft-expired", expired, "HOLD")

    false_outcomes = sum(item["actual"] != item["expected"] for item in scenarios)
    return {
        "schema": "truepanel.holodeck-aegis-coverage-envelope/v1",
        "experiment_id": "TP-EXP-0032",
        "simulation": True,
        "field_validated": False,
        "result": "PASS" if false_outcomes == 0 else "FAIL",
        "measurements": {
            "scenarios": len(scenarios),
            "ready": sum(
                item["actual"] == "READY_FOR_INDEPENDENT_ENVELOPE_REVIEW"
                for item in scenarios
            ),
            "holds": sum(item["actual"] == "HOLD" for item in scenarios),
            "false_outcomes": false_outcomes,
            "false_ready": sum(
                item["expected"] == "HOLD"
                and item["actual"] == "READY_FOR_INDEPENDENT_ENVELOPE_REVIEW"
                for item in scenarios
            ),
            "draft_artifacts_created": 1,
            "envelopes_accepted": 0,
            "envelopes_installed": 0,
            "runtime_writes": 0,
            "production_writes": 0,
        },
        "scenarios": scenarios,
        "safety": {
            "production_keys": 0,
            "live_provider_access": False,
            "hardware_actions": 0,
            "automatic_acceptance": False,
            "control_authority": False,
        },
    }


__all__ = ["run_coverage_envelope_rehearsal"]
