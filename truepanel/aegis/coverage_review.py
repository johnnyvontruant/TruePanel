"""Two-person review boundary for an appraised Recovery Coverage candidate.

The review verifies operator-owned detached signatures over exact, canonical
content.  Its strongest result permits drafting a successor AIRWORTHINESS
envelope; it never accepts the candidate or creates, installs, or promotes an
envelope.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from .acceptance import TRUST_POLICY_SCHEMA
from .coverage_appraisal import APPRAISAL_SCHEMA, semantic_sha256
from .ssh_verifier import DEFAULT_NAMESPACE

REVIEW_PACKET_SCHEMA = "truepanel.aegis-coverage-review-packet/v1"
REVIEW_RECEIPT_SCHEMA = "truepanel.aegis-coverage-review-receipt/v1"
REVIEW_DECISION = "APPROVE_FOR_SUCCESSOR_ENVELOPE_DRAFT"
SignatureVerifier = Callable[[str, bytes, str], bool]

_PACKET_FIELDS = {
    "schema",
    "purpose",
    "subjects",
    "required_reviewers",
    "required_key_type",
    "signature_namespace",
    "success_boundary",
    "candidate_accepted",
    "successor_envelope_created",
    "automatic_acceptance",
    "signing_authority",
    "control_authority",
}
_SUBJECT_FIELDS = {
    "accepted_matrix_sha256",
    "candidate_sha256",
    "appraisal_sha256",
    "appraisal_policy_sha256",
}
_RECEIPT_FIELDS = {
    "schema",
    "receipt_id",
    "decision",
    "packet_sha256",
    "issued_at",
    "expires_at",
    "environment",
    "signatures",
}
_STATEMENT_FIELDS = _RECEIPT_FIELDS - {"signatures"}


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _timestamp(value: Any) -> float | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    result = parsed.astimezone(UTC).timestamp()
    return result if math.isfinite(result) else None


def build_identity_review_packet(
    *,
    accepted_matrix: Mapping[str, Any],
    candidate: Mapping[str, Any],
    appraisal: Mapping[str, Any],
) -> dict[str, Any]:
    """Create portable review material without any key or signature."""

    return {
        "schema": REVIEW_PACKET_SCHEMA,
        "purpose": "independent-review-before-successor-envelope-draft",
        "subjects": {
            "accepted_matrix_sha256": semantic_sha256(accepted_matrix),
            "candidate_sha256": semantic_sha256(candidate),
            "appraisal_sha256": semantic_sha256(appraisal),
            "appraisal_policy_sha256": appraisal.get("policy_sha256"),
        },
        "required_reviewers": 2,
        "required_key_type": "ssh-ed25519",
        "signature_namespace": DEFAULT_NAMESPACE,
        "success_boundary": "ELIGIBLE_FOR_SUCCESSOR_ENVELOPE_DRAFT",
        "candidate_accepted": False,
        "successor_envelope_created": False,
        "automatic_acceptance": False,
        "signing_authority": False,
        "control_authority": False,
    }


def validate_identity_review_packet(
    packet: Mapping[str, Any],
    *,
    accepted_matrix: Mapping[str, Any],
    candidate: Mapping[str, Any],
    appraisal: Mapping[str, Any],
) -> tuple[str, ...]:
    """Return every packet defect; an empty result means reviewable only."""

    failures: list[str] = []
    if set(packet) != _PACKET_FIELDS or packet.get("schema") != REVIEW_PACKET_SCHEMA:
        failures.append("ReviewPacketShapeInvalid")
    subjects = packet.get("subjects")
    if not isinstance(subjects, Mapping) or set(subjects) != _SUBJECT_FIELDS:
        failures.append("ReviewSubjectsInvalid")
        subjects = {}
    expected = {
        "accepted_matrix_sha256": semantic_sha256(accepted_matrix),
        "candidate_sha256": semantic_sha256(candidate),
        "appraisal_sha256": semantic_sha256(appraisal),
        "appraisal_policy_sha256": appraisal.get("policy_sha256"),
    }
    if dict(subjects) != expected:
        failures.append("ReviewSubjectBindingInvalid")
    if (
        candidate.get("accepted") is not False
        or candidate.get("automatic_acceptance") is not False
        or appraisal.get("schema") != APPRAISAL_SCHEMA
        or appraisal.get("status") != "READY_FOR_INDEPENDENT_REVIEW"
        or appraisal.get("independent_review_complete") is not False
        or appraisal.get("candidate_accepted") is not False
    ):
        failures.append("AppraisedCandidateNotReviewable")
    expected_controls = {
        "purpose": "independent-review-before-successor-envelope-draft",
        "required_reviewers": 2,
        "required_key_type": "ssh-ed25519",
        "signature_namespace": DEFAULT_NAMESPACE,
        "success_boundary": "ELIGIBLE_FOR_SUCCESSOR_ENVELOPE_DRAFT",
        "candidate_accepted": False,
        "successor_envelope_created": False,
        "automatic_acceptance": False,
        "signing_authority": False,
        "control_authority": False,
    }
    if any(packet.get(name) != value for name, value in expected_controls.items()):
        failures.append("ReviewBoundaryInvalid")
    return tuple(dict.fromkeys(failures))


def coverage_review_statement(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact statement covered by every detached signature."""

    return {field: receipt.get(field) for field in sorted(_STATEMENT_FIELDS)}


def prepare_identity_review_handoff(
    *,
    accepted_matrix: Mapping[str, Any],
    candidate: Mapping[str, Any],
    appraisal: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose an unsigned runtime handoff without pretending review occurred."""

    packet = build_identity_review_packet(
        accepted_matrix=accepted_matrix,
        candidate=candidate,
        appraisal=appraisal,
    )
    failures = validate_identity_review_packet(
        packet,
        accepted_matrix=accepted_matrix,
        candidate=candidate,
        appraisal=appraisal,
    )
    return {
        "schema": REVIEW_PACKET_SCHEMA,
        "status": "AWAITING_INDEPENDENT_SIGNATURES" if not failures else "HOLD",
        "reason": "ReviewPacketPrepared" if not failures else failures[0],
        "packet_sha256": semantic_sha256(packet),
        "required_reviewers": 2,
        "valid_reviewers": 0,
        "production_keys_present": False,
        "independent_review_complete": False,
        "candidate_accepted": False,
        "successor_envelope_created": False,
        "automatic_acceptance": False,
        "runtime_writes": 0,
        "production_mutation": False,
        "control_authority": False,
    }


def evaluate_identity_review_receipt(
    *,
    packet: Mapping[str, Any],
    receipt: Mapping[str, Any],
    accepted_matrix: Mapping[str, Any],
    candidate: Mapping[str, Any],
    appraisal: Mapping[str, Any],
    trust_policy: Mapping[str, Any],
    verifier: SignatureVerifier,
    now: float,
) -> dict[str, Any]:
    """Verify two-person review without accepting or installing its subject."""

    conditions: list[dict[str, Any]] = []

    def add(name: str, passed: bool, reason: str) -> None:
        conditions.append({"condition": name, "passed": bool(passed), "reason": reason})

    packet_failures = validate_identity_review_packet(
        packet,
        accepted_matrix=accepted_matrix,
        candidate=candidate,
        appraisal=appraisal,
    )
    add(
        "review_packet",
        not packet_failures,
        "ReviewPacketBound" if not packet_failures else packet_failures[0],
    )
    receipt_shape = (
        set(receipt) == _RECEIPT_FIELDS
        and receipt.get("schema") == REVIEW_RECEIPT_SCHEMA
        and receipt.get("decision") == REVIEW_DECISION
        and receipt.get("packet_sha256") == semantic_sha256(packet)
    )
    add(
        "review_receipt",
        receipt_shape,
        "ReviewReceiptBound" if receipt_shape else "ReviewReceiptInvalid",
    )
    issued = _timestamp(receipt.get("issued_at"))
    expires = _timestamp(receipt.get("expires_at"))
    fresh = (
        issued is not None
        and expires is not None
        and issued <= float(now) < expires
        and 0 < expires - issued <= 24 * 60 * 60
    )
    add("review_freshness", fresh, "ReviewFresh" if fresh else "ReviewExpiredOrInvalid")

    threshold = trust_policy.get("threshold")
    keys = trust_policy.get("keys")
    key_items = (
        [dict(item) for item in keys if isinstance(item, Mapping)]
        if isinstance(keys, Sequence) and not isinstance(keys, (str, bytes))
        else []
    )
    key_ids = [str(item.get("key_id") or "") for item in key_items]
    reviewers = [str(item.get("reviewer_id") or "") for item in key_items]
    policy_valid = (
        trust_policy.get("schema") == TRUST_POLICY_SCHEMA
        and set(trust_policy) == {"schema", "threshold", "keys"}
        and threshold == 2
        and len(key_items) == 2
        and len(set(key_ids)) == 2
        and len(set(reviewers)) == 2
        and all(key_ids)
        and all(reviewers)
    )
    add(
        "separation_of_duty",
        policy_valid,
        "TwoPersonPolicyValid" if policy_valid else "TwoPersonPolicyInvalid",
    )
    key_map = {str(item.get("key_id")): item for item in key_items}
    statement = _canonical(coverage_review_statement(receipt))
    valid_reviewers: set[str] = set()
    valid_keys: set[str] = set()
    signatures = receipt.get("signatures")
    if isinstance(signatures, Sequence) and not isinstance(signatures, (str, bytes)):
        for signature in signatures:
            if not isinstance(signature, Mapping):
                continue
            key_id = str(signature.get("key_id") or "")
            reviewer = str(signature.get("reviewer_id") or "")
            key = key_map.get(key_id)
            if key is None or key.get("reviewer_id") != reviewer:
                continue
            valid_from = _timestamp(key.get("valid_from"))
            valid_until = _timestamp(key.get("valid_until"))
            revoked_at = _timestamp(key.get("revoked_at")) if key.get("revoked_at") else None
            lifecycle_ok = (
                issued is not None
                and valid_from is not None
                and valid_until is not None
                and valid_from <= issued < valid_until
                and (revoked_at is None or issued < revoked_at)
            )
            try:
                verified = lifecycle_ok and verifier(
                    key_id, statement, str(signature.get("signature") or "")
                )
            except Exception:
                verified = False
            if verified:
                valid_keys.add(key_id)
                valid_reviewers.add(reviewer)
    quorum = policy_valid and len(valid_keys) == 2 and len(valid_reviewers) == 2
    add(
        "independent_signature_quorum",
        quorum,
        "IndependentReviewQuorumMet" if quorum else "IndependentReviewQuorumMissing",
    )
    failed = [item for item in conditions if item["passed"] is not True]
    return {
        "schema": REVIEW_RECEIPT_SCHEMA,
        "status": "ELIGIBLE_FOR_SUCCESSOR_ENVELOPE_DRAFT" if not failed else "HOLD",
        "reason": "IndependentCoverageReviewVerified" if not failed else failed[0]["reason"],
        "packet_sha256": semantic_sha256(packet),
        "receipt_sha256": semantic_sha256(receipt),
        "conditions": conditions,
        "valid_reviewer_count": len(valid_reviewers),
        "required_reviewer_count": 2,
        "candidate_accepted": False,
        "successor_envelope_created": False,
        "candidate_installed": False,
        "automatic_acceptance": False,
        "private_key_material": False,
        "runtime_writes": 0,
        "production_mutation": False,
        "control_authority": False,
    }


__all__ = [
    "REVIEW_DECISION",
    "REVIEW_PACKET_SCHEMA",
    "REVIEW_RECEIPT_SCHEMA",
    "build_identity_review_packet",
    "coverage_review_statement",
    "evaluate_identity_review_receipt",
    "prepare_identity_review_handoff",
    "validate_identity_review_packet",
]
