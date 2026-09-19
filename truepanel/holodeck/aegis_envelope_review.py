"""Deterministic checkride for independent successor-envelope review."""

from __future__ import annotations

import json
import os
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
    REVIEW_RECEIPT_SCHEMA,
    build_identity_review_packet,
)
from truepanel.aegis.envelope_review import (
    ENVELOPE_REVIEW_DECISION,
    ENVELOPE_REVIEW_RECEIPT_SCHEMA,
    build_envelope_review_packet,
    envelope_review_statement,
    evaluate_envelope_review_receipt,
)
from truepanel.aegis.identity_coverage import (
    build_identity_coverage_candidate,
    rehearse_identity_coverage_contract,
)
from truepanel.aegis.rehearsal import rehearse_recovery_paths
from truepanel.aegis.ssh_verifier import DEFAULT_NAMESPACE, OpenSshSignatureVerifier
from truepanel.holodeck.aegis_coverage_envelope import _key, _sign

NOW = datetime(2026, 9, 19, 4, 30, tzinfo=UTC).timestamp()
UPSTREAM_EVIDENCE_SHA256 = (
    "f2911671a590ea35290d8f18cb0aa90c9a204f40c4d5acfa849dc8fe202b44b3"
)


def _materials() -> dict[str, Any]:
    accepted_envelope = load_assurance_envelope()
    accepted_matrix = coverage_matrix(rehearse_recovery_paths())
    candidate = build_identity_coverage_candidate(
        accepted_matrix, rehearse_identity_coverage_contract()
    )
    appraisal = appraise_identity_coverage_candidate(
        accepted_matrix=accepted_matrix, candidate=candidate
    )
    coverage_packet = build_identity_review_packet(
        accepted_matrix=accepted_matrix,
        candidate=candidate,
        appraisal=appraisal,
    )
    coverage_review = {
        "schema": REVIEW_RECEIPT_SCHEMA,
        "status": "ELIGIBLE_FOR_SUCCESSOR_ENVELOPE_DRAFT",
        "reason": "IndependentCoverageReviewVerified",
        "packet_sha256": semantic_sha256(coverage_packet),
        "receipt_sha256": semantic_sha256(
            {
                "experiment_id": "TP-EXP-0032",
                "evidence_sha256": UPSTREAM_EVIDENCE_SHA256,
            }
        ),
        "valid_reviewer_count": 2,
        "candidate_accepted": False,
        "successor_envelope_created": False,
        "automatic_acceptance": False,
        "control_authority": False,
    }
    draft_result = prepare_coverage_successor_draft(
        accepted_envelope=accepted_envelope,
        accepted_matrix=accepted_matrix,
        candidate_matrix=candidate,
        appraisal=appraisal,
        review_result=coverage_review,
        issued_at="2026-09-19T04:05:00Z",
        expires_at="2026-12-15T04:05:00Z",
    )
    return {
        "accepted_envelope": accepted_envelope,
        "accepted_matrix": accepted_matrix,
        "candidate": candidate,
        "appraisal": appraisal,
        "coverage_review": coverage_review,
        "draft_result": draft_result,
    }


def run_envelope_review_rehearsal() -> dict[str, Any]:
    """Prove review eligibility while stopping before manual acceptance."""

    material = _materials()
    packet = build_envelope_review_packet(**material)
    scenarios: list[dict[str, str]] = []
    root = Path(__file__).resolve().parents[1]

    with TemporaryDirectory(prefix="truepanel-holodeck-envelope-review-") as temporary:
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
                    "reviewer_id": "airworthiness-reviewer-a",
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
            "schema": ENVELOPE_REVIEW_RECEIPT_SCHEMA,
            "receipt_id": "identity-envelope-review-checkride-v1",
            "decision": ENVELOPE_REVIEW_DECISION,
            "packet_sha256": semantic_sha256(packet),
            "issued_at": "2026-09-19T04:00:00Z",
            "expires_at": "2026-09-20T04:00:00Z",
            "environment": "HOLODECK",
            "signatures": [],
        }
        statement = json.dumps(
            envelope_review_statement(receipt),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        receipt["signatures"] = [
            {
                "key_id": "reviewer-a",
                "reviewer_id": "airworthiness-reviewer-a",
                "signature": _sign(key_a, statement, temporary_root, "lane-a"),
            },
            {
                "key_id": "reviewer-b",
                "reviewer_id": "safety-reviewer-b",
                "signature": _sign(key_b, statement, temporary_root, "lane-b"),
            },
        ]

        def evaluate(
            name: str,
            expected: str,
            *,
            packet_value: dict[str, Any] | None = None,
            receipt_value: dict[str, Any] | None = None,
            material_value: dict[str, Any] | None = None,
            verifier_namespace: str = DEFAULT_NAMESPACE,
        ) -> None:
            supplied = material_value or material
            result = evaluate_envelope_review_receipt(
                packet=packet_value or packet,
                receipt=receipt_value or receipt,
                trust_policy=policy,
                verifier=OpenSshSignatureVerifier(
                    allowed,
                    namespace=verifier_namespace,
                    expected_key_ids=("reviewer-a", "reviewer-b"),
                ),
                now=NOW,
                package_root=root,
                **supplied,
            )
            scenarios.append(
                {
                    "name": name,
                    "expected": expected,
                    "actual": result["status"],
                    "reason": result["reason"],
                }
            )

        evaluate("exact-independent-review", "ELIGIBLE_FOR_MANUAL_ENVELOPE_ACCEPTANCE")

        one_reviewer = deepcopy(receipt)
        one_reviewer["signatures"] = one_reviewer["signatures"][:1]
        evaluate("one-reviewer", "HOLD", receipt_value=one_reviewer)

        expired = deepcopy(receipt)
        expired["expires_at"] = "2026-09-19T04:15:00Z"
        evaluate("expired-receipt", "HOLD", receipt_value=expired)

        extended_packet = deepcopy(packet)
        extended_packet["presentation_note"] = "unsigned"
        evaluate("packet-extension", "HOLD", packet_value=extended_packet)

        changed_draft = deepcopy(material)
        changed_draft["draft_result"] = deepcopy(material["draft_result"])
        changed_draft["draft_result"]["draft"]["expires_at"] = "2027-01-01T00:00:00Z"
        evaluate("draft-after-review-tamper", "HOLD", material_value=changed_draft)

        accepted_draft = deepcopy(material)
        accepted_draft["draft_result"] = deepcopy(material["draft_result"])
        accepted_draft["draft_result"]["draft"]["accepted"] = True
        evaluate("automatic-acceptance", "HOLD", material_value=accepted_draft)

        changed_candidate = deepcopy(material)
        changed_candidate["candidate"] = deepcopy(material["candidate"])
        changed_candidate["candidate"]["review_required"] = False
        evaluate("candidate-substitution", "HOLD", material_value=changed_candidate)

        changed_predecessor = deepcopy(material)
        changed_predecessor["accepted_envelope"] = deepcopy(material["accepted_envelope"])
        changed_predecessor["accepted_envelope"]["envelope_id"] = "substituted"
        evaluate("predecessor-substitution", "HOLD", material_value=changed_predecessor)

        evaluate(
            "namespace-mismatch",
            "HOLD",
            verifier_namespace="truepanel-aegis-wrong-purpose@truepanel",
        )

        duplicated_policy = deepcopy(policy)
        duplicated_policy["keys"][1]["reviewer_id"] = duplicated_policy["keys"][0][
            "reviewer_id"
        ]
        result = evaluate_envelope_review_receipt(
            packet=packet,
            receipt=receipt,
            trust_policy=duplicated_policy,
            verifier=OpenSshSignatureVerifier(
                allowed, expected_key_ids=("reviewer-a", "reviewer-b")
            ),
            now=NOW,
            package_root=root,
            **material,
        )
        scenarios.append(
            {
                "name": "duplicate-policy-identity",
                "expected": "HOLD",
                "actual": result["status"],
                "reason": result["reason"],
            }
        )

    false_outcomes = sum(item["actual"] != item["expected"] for item in scenarios)
    return {
        "schema": "truepanel.holodeck-aegis-envelope-review/v1",
        "experiment_id": "TP-EXP-0033",
        "simulation": True,
        "field_validated": False,
        "result": "PASS" if false_outcomes == 0 else "FAIL",
        "measurements": {
            "scenarios": len(scenarios),
            "eligible": sum(
                item["actual"] == "ELIGIBLE_FOR_MANUAL_ENVELOPE_ACCEPTANCE"
                for item in scenarios
            ),
            "holds": sum(item["actual"] == "HOLD" for item in scenarios),
            "false_outcomes": false_outcomes,
            "false_eligible": sum(
                item["expected"] == "HOLD"
                and item["actual"] == "ELIGIBLE_FOR_MANUAL_ENVELOPE_ACCEPTANCE"
                for item in scenarios
            ),
            "envelopes_accepted": 0,
            "envelopes_installed": 0,
            "candidate_acceptances": 0,
            "runtime_writes": 0,
            "production_writes": 0,
        },
        "scenarios": scenarios,
        "safety": {
            "production_keys": 0,
            "live_provider_access": False,
            "hardware_actions": 0,
            "manual_acceptance_required": True,
            "automatic_acceptance": False,
            "control_authority": False,
        },
    }


__all__ = ["run_envelope_review_rehearsal"]
