"""Single-operator, development-only AEGIS review receipts.

This module represents TruePanel's actual small-team authority model without
pretending that AI-assisted review is a second human approval.  Its output is
deliberately a different type from production acceptance receipts.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from .acceptance import semantic_sha256

DEVELOPMENT_POLICY_SCHEMA = "truepanel.aegis-single-operator-development-policy/v1"
DEVELOPMENT_PACKET_SCHEMA = "truepanel.aegis-single-operator-development-packet/v1"
DEVELOPMENT_RECEIPT_SCHEMA = "truepanel.aegis-single-operator-development-receipt/v1"
DEVELOPMENT_RESULT_SCHEMA = "truepanel.aegis-single-operator-development-result/v1"
DEVELOPMENT_NAMESPACE = "truepanel-aegis-development-review-v1@truepanel"

SignatureVerifier = Callable[[str, bytes, str], bool]

_PACKET_FIELDS = {
    "schema",
    "review_id",
    "source_commit",
    "policy_sha256",
    "candidate_sha256",
    "holodeck_evidence_sha256",
    "coverage_matrix_sha256",
    "reviewer_report_sha256",
    "scope",
    "human_approver_count",
    "ai_review_is_approval",
    "production_authority",
    "deployment_authority",
    "hardware_authority",
    "storage_write_authority",
    "automatic_promotion",
}
_RECEIPT_FIELDS = {
    "schema",
    "receipt_id",
    "packet_sha256",
    "decision",
    "operator_id",
    "key_id",
    "issued_at",
    "expires_at",
    "environment",
    "signature",
    "production_authority",
    "deployment_authority",
    "hardware_authority",
    "storage_write_authority",
    "automatic_promotion",
}


def _timestamp(value: Any) -> float | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    result = parsed.astimezone(UTC).timestamp()
    return result if math.isfinite(result) else None


def development_statement(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact statement covered by the operator signature."""

    return {
        field: receipt.get(field) for field in sorted(_RECEIPT_FIELDS - {"signature"})
    }


def build_development_packet(
    *,
    review_id: str,
    source_commit: str,
    policy: Mapping[str, Any],
    candidate: Mapping[str, Any],
    holodeck_evidence: Mapping[str, Any],
    coverage_matrix: Mapping[str, Any],
    reviewer_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind review inputs while granting no operational authority."""

    return {
        "schema": DEVELOPMENT_PACKET_SCHEMA,
        "review_id": review_id,
        "source_commit": source_commit,
        "policy_sha256": semantic_sha256(policy),
        "candidate_sha256": semantic_sha256(candidate),
        "holodeck_evidence_sha256": semantic_sha256(holodeck_evidence),
        "coverage_matrix_sha256": semantic_sha256(coverage_matrix),
        "reviewer_report_sha256": semantic_sha256(reviewer_report),
        "scope": "DEVELOPMENT_ONLY",
        "human_approver_count": 1,
        "ai_review_is_approval": False,
        "production_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "automatic_promotion": False,
    }


def evaluate_development_receipt(
    *,
    packet: Mapping[str, Any],
    receipt: Mapping[str, Any],
    policy: Mapping[str, Any],
    candidate: Mapping[str, Any],
    holodeck_evidence: Mapping[str, Any],
    coverage_matrix: Mapping[str, Any],
    reviewer_report: Mapping[str, Any],
    verifier: SignatureVerifier,
    now: float,
    consumed_receipts: Sequence[str] = (),
) -> dict[str, Any]:
    """Verify one human signature and deterministic evidence, fail closed."""

    conditions: list[dict[str, Any]] = []

    def add(name: str, passed: bool, reason: str) -> None:
        conditions.append({"condition": name, "passed": bool(passed), "reason": reason})

    packet_exact = set(packet) == _PACKET_FIELDS
    receipt_exact = set(receipt) == _RECEIPT_FIELDS
    add(
        "packet_fields",
        packet_exact,
        "PacketFieldsExact" if packet_exact else "PacketFieldsInvalid",
    )
    add(
        "receipt_fields",
        receipt_exact,
        "ReceiptFieldsExact" if receipt_exact else "ReceiptFieldsInvalid",
    )
    add(
        "schemas",
        packet.get("schema") == DEVELOPMENT_PACKET_SCHEMA
        and receipt.get("schema") == DEVELOPMENT_RECEIPT_SCHEMA
        and policy.get("schema") == DEVELOPMENT_POLICY_SCHEMA,
        "DevelopmentSchemasMatched",
    )
    expected_policy_fields = {
        "schema",
        "policy_id",
        "operator_id",
        "key_id",
        "maximum_age_seconds",
        "environment",
        "namespace",
        "production_authority",
        "deployment_authority",
        "hardware_authority",
        "storage_write_authority",
        "automatic_promotion",
    }
    policy_valid = (
        set(policy) == expected_policy_fields
        and policy.get("environment") == "DEVELOPMENT"
        and policy.get("namespace") == DEVELOPMENT_NAMESPACE
        and isinstance(policy.get("maximum_age_seconds"), int)
        and not isinstance(policy.get("maximum_age_seconds"), bool)
        and 0 < policy.get("maximum_age_seconds", 0) <= 24 * 60 * 60
        and all(
            policy.get(name) is False
            for name in (
                "production_authority",
                "deployment_authority",
                "hardware_authority",
                "storage_write_authority",
                "automatic_promotion",
            )
        )
    )
    add(
        "development_policy",
        policy_valid,
        "DevelopmentPolicyValid" if policy_valid else "DevelopmentPolicyInvalid",
    )
    bindings = (
        packet.get("policy_sha256") == semantic_sha256(policy)
        and packet.get("candidate_sha256") == semantic_sha256(candidate)
        and packet.get("holodeck_evidence_sha256") == semantic_sha256(holodeck_evidence)
        and packet.get("coverage_matrix_sha256") == semantic_sha256(coverage_matrix)
        and packet.get("reviewer_report_sha256") == semantic_sha256(reviewer_report)
        and receipt.get("packet_sha256") == semantic_sha256(packet)
    )
    add(
        "content_bindings",
        bindings,
        "ReviewInputsBound" if bindings else "ReviewInputDigestMismatch",
    )
    source_bound = (
        isinstance(packet.get("source_commit"), str)
        and len(packet.get("source_commit", "")) == 40
        and candidate.get("source_commit") == packet.get("source_commit")
    )
    add(
        "source_commit",
        source_bound,
        "SourceCommitBound" if source_bound else "SourceCommitInvalid",
    )
    evidence_valid = (
        holodeck_evidence.get("hardware_isolated") is True
        and holodeck_evidence.get("control_authority") is False
        and holodeck_evidence.get("false_eligible_paths") == 0
        and holodeck_evidence.get("status") == "PASS"
    )
    add(
        "holodeck_rehearsal",
        evidence_valid,
        "HoloDeckEvidenceVerified" if evidence_valid else "HoloDeckEvidenceInvalid",
    )
    coverage_valid = (
        coverage_matrix.get("gaps") == 0
        and coverage_matrix.get("trusted") == coverage_matrix.get("total")
        and isinstance(coverage_matrix.get("total"), int)
        and coverage_matrix.get("total", 0) > 0
    )
    add(
        "recovery_coverage",
        coverage_valid,
        "RecoveryCoverageComplete" if coverage_valid else "RecoveryCoverageIncomplete",
    )
    report_valid = (
        reviewer_report.get("reviewer_kind") == "AI_ASSISTED_ENGINEERING_EVIDENCE"
        and reviewer_report.get("approval_authority") is False
        and reviewer_report.get("checks_complete") is True
        and reviewer_report.get("open_blockers") == []
    )
    add(
        "reviewer_evidence",
        report_valid,
        "ReviewerEvidenceBound" if report_valid else "ReviewerEvidenceInvalid",
    )
    authority_fields = (
        packet.get("scope") == "DEVELOPMENT_ONLY"
        and packet.get("human_approver_count") == 1
        and packet.get("ai_review_is_approval") is False
        and receipt.get("decision") == "APPROVE_DEVELOPMENT_CANDIDATE_REVIEW_ONLY"
        and receipt.get("environment") == "DEVELOPMENT"
        and all(
            packet.get(name) is False and receipt.get(name) is False
            for name in (
                "production_authority",
                "deployment_authority",
                "hardware_authority",
                "storage_write_authority",
                "automatic_promotion",
            )
        )
    )
    add(
        "authority_ceiling",
        authority_fields,
        "DevelopmentAuthorityBound"
        if authority_fields
        else "AuthorityEscalationRejected",
    )
    issued = _timestamp(receipt.get("issued_at"))
    expires = _timestamp(receipt.get("expires_at"))
    maximum_age = policy.get("maximum_age_seconds", 0) if policy_valid else 0
    fresh = (
        issued is not None
        and expires is not None
        and issued <= float(now) < expires
        and 0 < expires - issued <= maximum_age
    )
    add("freshness", fresh, "ReceiptFresh" if fresh else "ReceiptExpiredOrInvalid")
    identity = receipt.get("operator_id") == policy.get("operator_id") and receipt.get(
        "key_id"
    ) == policy.get("key_id")
    add(
        "operator_identity",
        identity,
        "OperatorIdentityBound" if identity else "OperatorIdentityMismatch",
    )
    receipt_digest = semantic_sha256(receipt)
    unused = receipt_digest not in set(consumed_receipts)
    add("replay", unused, "ReceiptUnused" if unused else "ReceiptAlreadyConsumed")
    try:
        signed = identity and verifier(
            str(receipt.get("key_id") or ""),
            __import__("json")
            .dumps(
                development_statement(receipt),
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            .encode(),
            str(receipt.get("signature") or ""),
        )
    except Exception:
        signed = False
    add(
        "operator_signature",
        signed,
        "OperatorSignatureVerified" if signed else "OperatorSignatureInvalid",
    )

    failed = [item for item in conditions if not item["passed"]]
    return {
        "schema": DEVELOPMENT_RESULT_SCHEMA,
        "status": "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW" if not failed else "HOLD",
        "reason": "SingleOperatorDevelopmentReviewVerified"
        if not failed
        else failed[0]["reason"],
        "conditions": conditions,
        "packet_sha256": semantic_sha256(packet),
        "receipt_sha256": receipt_digest,
        "human_approver_count": 1 if signed else 0,
        "ai_review_is_approval": False,
        "production_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "automatic_promotion": False,
        "receipt_consumed": False,
        "runtime_writes": 0,
    }


def authority_boundary(artifact: Mapping[str, Any], capability: str) -> dict[str, Any]:
    """Explicitly deny development receipts at every stronger consumer."""

    allowed = (
        capability == "development_candidate_review"
        and artifact.get("schema") == DEVELOPMENT_RESULT_SCHEMA
        and artifact.get("status") == "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW"
    )
    return {
        "status": "ALLOWED" if allowed else "DENIED",
        "capability": capability,
        "reason": "DevelopmentReviewOnly"
        if allowed
        else "DevelopmentReceiptHasNoRequestedAuthority",
        "production_mutation": False,
        "control_authority": False,
    }


__all__ = [
    "DEVELOPMENT_NAMESPACE",
    "DEVELOPMENT_PACKET_SCHEMA",
    "DEVELOPMENT_POLICY_SCHEMA",
    "DEVELOPMENT_RECEIPT_SCHEMA",
    "DEVELOPMENT_RESULT_SCHEMA",
    "authority_boundary",
    "build_development_packet",
    "development_statement",
    "evaluate_development_receipt",
]
