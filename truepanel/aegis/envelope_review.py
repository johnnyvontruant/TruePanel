"""Independent review boundary for a successor AIRWORTHINESS envelope draft.

Reviewing the draft is deliberately distinct from accepting it.  This module
can prove two operator-owned signatures over exact content, but it cannot
accept, install, promote, or deploy an envelope.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .acceptance import TRUST_POLICY_SCHEMA
from .coverage_appraisal import semantic_sha256
from .coverage_envelope import (
    COVERAGE_ENVELOPE_DRAFT_SCHEMA,
    prepare_coverage_successor_draft,
)
from .requalification import envelope_sha256
from .ssh_verifier import DEFAULT_NAMESPACE

ENVELOPE_REVIEW_PACKET_SCHEMA = "truepanel.aegis-envelope-review-packet/v1"
ENVELOPE_REVIEW_RECEIPT_SCHEMA = "truepanel.aegis-envelope-review-receipt/v1"
ENVELOPE_REVIEW_DECISION = "APPROVE_FOR_MANUAL_ENVELOPE_ACCEPTANCE"
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
    "envelope_accepted",
    "envelope_installed",
    "automatic_acceptance",
    "signing_authority",
    "control_authority",
}
_SUBJECT_FIELDS = {
    "accepted_envelope_sha256",
    "accepted_matrix_sha256",
    "candidate_sha256",
    "appraisal_sha256",
    "coverage_review_packet_sha256",
    "coverage_review_receipt_sha256",
    "envelope_draft_sha256",
    "envelope_review_evaluator_sha256",
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
_SIGNATURE_FIELDS = {"key_id", "reviewer_id", "signature"}
_KEY_FIELDS = {"key_id", "reviewer_id", "valid_from", "valid_until"}


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp(value: Any) -> float | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    result = parsed.astimezone(UTC).timestamp()
    return result if math.isfinite(result) else None


def _expected_draft(
    *,
    accepted_envelope: Mapping[str, Any],
    accepted_matrix: Mapping[str, Any],
    candidate: Mapping[str, Any],
    appraisal: Mapping[str, Any],
    coverage_review: Mapping[str, Any],
    draft_result: Mapping[str, Any],
    package_root: Path | None,
) -> dict[str, Any] | None:
    draft = draft_result.get("draft")
    if not isinstance(draft, Mapping):
        return None
    rebuilt = prepare_coverage_successor_draft(
        accepted_envelope=accepted_envelope,
        accepted_matrix=accepted_matrix,
        candidate_matrix=candidate,
        appraisal=appraisal,
        review_result=coverage_review,
        issued_at=str(draft.get("issued_at") or ""),
        expires_at=str(draft.get("expires_at") or ""),
        package_root=package_root,
    )
    expected = rebuilt.get("draft")
    return dict(expected) if isinstance(expected, Mapping) else None


def build_envelope_review_packet(
    *,
    accepted_envelope: Mapping[str, Any],
    accepted_matrix: Mapping[str, Any],
    candidate: Mapping[str, Any],
    appraisal: Mapping[str, Any],
    coverage_review: Mapping[str, Any],
    draft_result: Mapping[str, Any],
    package_root: Path | None = None,
) -> dict[str, Any]:
    """Create portable review material without a private key or signature."""

    draft = draft_result.get("draft")
    draft_digest = envelope_sha256(draft) if isinstance(draft, Mapping) else None
    root = package_root or Path(__file__).resolve().parents[1]
    return {
        "schema": ENVELOPE_REVIEW_PACKET_SCHEMA,
        "purpose": "independent-review-before-manual-envelope-acceptance",
        "subjects": {
            "accepted_envelope_sha256": envelope_sha256(accepted_envelope),
            "accepted_matrix_sha256": semantic_sha256(accepted_matrix),
            "candidate_sha256": semantic_sha256(candidate),
            "appraisal_sha256": semantic_sha256(appraisal),
            "coverage_review_packet_sha256": coverage_review.get("packet_sha256"),
            "coverage_review_receipt_sha256": coverage_review.get("receipt_sha256"),
            "envelope_draft_sha256": draft_digest,
            "envelope_review_evaluator_sha256": _sha256_file(
                root / "aegis/envelope_review.py"
            ),
        },
        "required_reviewers": 2,
        "required_key_type": "ssh-ed25519",
        "signature_namespace": DEFAULT_NAMESPACE,
        "success_boundary": "ELIGIBLE_FOR_MANUAL_ENVELOPE_ACCEPTANCE",
        "candidate_accepted": False,
        "envelope_accepted": False,
        "envelope_installed": False,
        "automatic_acceptance": False,
        "signing_authority": False,
        "control_authority": False,
    }


def validate_envelope_review_packet(
    packet: Mapping[str, Any],
    *,
    accepted_envelope: Mapping[str, Any],
    accepted_matrix: Mapping[str, Any],
    candidate: Mapping[str, Any],
    appraisal: Mapping[str, Any],
    coverage_review: Mapping[str, Any],
    draft_result: Mapping[str, Any],
    package_root: Path | None = None,
) -> tuple[str, ...]:
    """Return every defect; an empty result means independently reviewable."""

    failures: list[str] = []
    if set(packet) != _PACKET_FIELDS or packet.get("schema") != ENVELOPE_REVIEW_PACKET_SCHEMA:
        failures.append("EnvelopeReviewPacketShapeInvalid")
    subjects = packet.get("subjects")
    if not isinstance(subjects, Mapping) or set(subjects) != _SUBJECT_FIELDS:
        failures.append("EnvelopeReviewSubjectsInvalid")
        subjects = {}
    expected_draft = _expected_draft(
        accepted_envelope=accepted_envelope,
        accepted_matrix=accepted_matrix,
        candidate=candidate,
        appraisal=appraisal,
        coverage_review=coverage_review,
        draft_result=draft_result,
        package_root=package_root,
    )
    supplied_draft = draft_result.get("draft")
    draft_bound = (
        draft_result.get("schema") == COVERAGE_ENVELOPE_DRAFT_SCHEMA
        and draft_result.get("status") == "READY_FOR_INDEPENDENT_ENVELOPE_REVIEW"
        and isinstance(supplied_draft, Mapping)
        and expected_draft is not None
        and envelope_sha256(supplied_draft) == envelope_sha256(expected_draft)
        and draft_result.get("draft_sha256") == envelope_sha256(expected_draft)
        and supplied_draft.get("accepted") is False
        and supplied_draft.get("installed") is False
        and supplied_draft.get("automatic_acceptance") is False
        and draft_result.get("successor_envelope_accepted") is False
        and draft_result.get("candidate_installed") is False
        and draft_result.get("control_authority") is False
    )
    if not draft_bound:
        failures.append("EnvelopeDraftNotReviewable")
    expected_subjects = {
        "accepted_envelope_sha256": envelope_sha256(accepted_envelope),
        "accepted_matrix_sha256": semantic_sha256(accepted_matrix),
        "candidate_sha256": semantic_sha256(candidate),
        "appraisal_sha256": semantic_sha256(appraisal),
        "coverage_review_packet_sha256": coverage_review.get("packet_sha256"),
        "coverage_review_receipt_sha256": coverage_review.get("receipt_sha256"),
        "envelope_draft_sha256": (
            envelope_sha256(expected_draft) if expected_draft is not None else None
        ),
        "envelope_review_evaluator_sha256": _sha256_file(
            (package_root or Path(__file__).resolve().parents[1])
            / "aegis/envelope_review.py"
        ),
    }
    if dict(subjects) != expected_subjects:
        failures.append("EnvelopeReviewSubjectBindingInvalid")
    expected_controls = {
        "purpose": "independent-review-before-manual-envelope-acceptance",
        "required_reviewers": 2,
        "required_key_type": "ssh-ed25519",
        "signature_namespace": DEFAULT_NAMESPACE,
        "success_boundary": "ELIGIBLE_FOR_MANUAL_ENVELOPE_ACCEPTANCE",
        "candidate_accepted": False,
        "envelope_accepted": False,
        "envelope_installed": False,
        "automatic_acceptance": False,
        "signing_authority": False,
        "control_authority": False,
    }
    if any(packet.get(name) != value for name, value in expected_controls.items()):
        failures.append("EnvelopeReviewBoundaryInvalid")
    return tuple(dict.fromkeys(failures))


def envelope_review_statement(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact statement covered by each detached signature."""

    return {field: receipt.get(field) for field in sorted(_STATEMENT_FIELDS)}


def prepare_envelope_review_handoff(
    *,
    accepted_envelope: Mapping[str, Any],
    accepted_matrix: Mapping[str, Any],
    candidate: Mapping[str, Any],
    appraisal: Mapping[str, Any],
    coverage_review: Mapping[str, Any],
    draft_result: Mapping[str, Any],
    package_root: Path | None = None,
) -> dict[str, Any]:
    """Expose an unsigned handoff without claiming envelope approval."""

    packet = build_envelope_review_packet(
        accepted_envelope=accepted_envelope,
        accepted_matrix=accepted_matrix,
        candidate=candidate,
        appraisal=appraisal,
        coverage_review=coverage_review,
        draft_result=draft_result,
        package_root=package_root,
    )
    failures = validate_envelope_review_packet(
        packet,
        accepted_envelope=accepted_envelope,
        accepted_matrix=accepted_matrix,
        candidate=candidate,
        appraisal=appraisal,
        coverage_review=coverage_review,
        draft_result=draft_result,
        package_root=package_root,
    )
    return {
        "schema": ENVELOPE_REVIEW_PACKET_SCHEMA,
        "status": "AWAITING_INDEPENDENT_ENVELOPE_SIGNATURES" if not failures else "HOLD",
        "reason": "EnvelopeReviewPacketPrepared" if not failures else failures[0],
        "packet_sha256": semantic_sha256(packet),
        "required_reviewers": 2,
        "valid_reviewer_count": 0,
        "production_keys_present": False,
        "independent_review_complete": False,
        "candidate_accepted": False,
        "envelope_accepted": False,
        "envelope_installed": False,
        "manual_acceptance_required": True,
        "automatic_acceptance": False,
        "runtime_writes": 0,
        "production_mutation": False,
        "control_authority": False,
    }


def evaluate_envelope_review_receipt(
    *,
    packet: Mapping[str, Any],
    receipt: Mapping[str, Any],
    accepted_envelope: Mapping[str, Any],
    accepted_matrix: Mapping[str, Any],
    candidate: Mapping[str, Any],
    appraisal: Mapping[str, Any],
    coverage_review: Mapping[str, Any],
    draft_result: Mapping[str, Any],
    trust_policy: Mapping[str, Any],
    verifier: SignatureVerifier,
    now: float,
    package_root: Path | None = None,
) -> dict[str, Any]:
    """Verify envelope review while preserving manual acceptance authority."""

    conditions: list[dict[str, Any]] = []

    def add(name: str, passed: bool, reason: str) -> None:
        conditions.append({"condition": name, "passed": bool(passed), "reason": reason})

    packet_failures = validate_envelope_review_packet(
        packet,
        accepted_envelope=accepted_envelope,
        accepted_matrix=accepted_matrix,
        candidate=candidate,
        appraisal=appraisal,
        coverage_review=coverage_review,
        draft_result=draft_result,
        package_root=package_root,
    )
    add(
        "envelope_review_packet",
        not packet_failures,
        "EnvelopeReviewPacketBound" if not packet_failures else packet_failures[0],
    )
    receipt_shape = (
        set(receipt) == _RECEIPT_FIELDS
        and receipt.get("schema") == ENVELOPE_REVIEW_RECEIPT_SCHEMA
        and receipt.get("decision") == ENVELOPE_REVIEW_DECISION
        and receipt.get("packet_sha256") == semantic_sha256(packet)
    )
    add(
        "envelope_review_receipt",
        receipt_shape,
        "EnvelopeReviewReceiptBound" if receipt_shape else "EnvelopeReviewReceiptInvalid",
    )
    issued = _timestamp(receipt.get("issued_at"))
    expires = _timestamp(receipt.get("expires_at"))
    fresh = (
        issued is not None
        and expires is not None
        and issued <= float(now) < expires
        and 0 < expires - issued <= 24 * 60 * 60
    )
    add(
        "envelope_review_freshness",
        fresh,
        "EnvelopeReviewFresh" if fresh else "EnvelopeReviewExpiredOrInvalid",
    )
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
        and trust_policy.get("threshold") == 2
        and len(key_items) == 2
        and len(set(key_ids)) == 2
        and len(set(reviewers)) == 2
        and all(key_ids)
        and all(reviewers)
        and all(
            set(item) in (_KEY_FIELDS, _KEY_FIELDS | {"revoked_at"})
            for item in key_items
        )
    )
    add(
        "envelope_review_separation_of_duty",
        policy_valid,
        "EnvelopeReviewPolicyValid" if policy_valid else "EnvelopeReviewPolicyInvalid",
    )
    key_map = {str(item.get("key_id")): item for item in key_items}
    statement = _canonical(envelope_review_statement(receipt))
    valid_keys: set[str] = set()
    valid_reviewers: set[str] = set()
    signatures = receipt.get("signatures")
    signatures_valid = (
        isinstance(signatures, Sequence)
        and not isinstance(signatures, (str, bytes))
        and len(signatures) == 2
        and all(
            isinstance(signature, Mapping) and set(signature) == _SIGNATURE_FIELDS
            for signature in signatures
        )
    )
    add(
        "envelope_review_signature_shape",
        signatures_valid,
        "EnvelopeReviewSignaturesStrict"
        if signatures_valid
        else "EnvelopeReviewSignaturesInvalid",
    )
    if signatures_valid:
        for signature in signatures:
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
    quorum = (
        policy_valid
        and signatures_valid
        and len(valid_keys) == 2
        and len(valid_reviewers) == 2
    )
    add(
        "envelope_review_signature_quorum",
        quorum,
        "EnvelopeReviewQuorumMet" if quorum else "EnvelopeReviewQuorumMissing",
    )
    failed = [item for item in conditions if item["passed"] is not True]
    return {
        "schema": ENVELOPE_REVIEW_RECEIPT_SCHEMA,
        "status": "ELIGIBLE_FOR_MANUAL_ENVELOPE_ACCEPTANCE" if not failed else "HOLD",
        "reason": "IndependentEnvelopeReviewVerified" if not failed else failed[0]["reason"],
        "packet_sha256": semantic_sha256(packet),
        "receipt_sha256": semantic_sha256(receipt),
        "conditions": conditions,
        "valid_reviewer_count": len(valid_reviewers),
        "required_reviewer_count": 2,
        "candidate_accepted": False,
        "envelope_accepted": False,
        "envelope_installed": False,
        "manual_acceptance_required": True,
        "automatic_acceptance": False,
        "private_key_material": False,
        "runtime_writes": 0,
        "production_mutation": False,
        "control_authority": False,
    }


__all__ = [
    "ENVELOPE_REVIEW_DECISION",
    "ENVELOPE_REVIEW_PACKET_SCHEMA",
    "ENVELOPE_REVIEW_RECEIPT_SCHEMA",
    "build_envelope_review_packet",
    "envelope_review_statement",
    "evaluate_envelope_review_receipt",
    "prepare_envelope_review_handoff",
    "validate_envelope_review_packet",
]
