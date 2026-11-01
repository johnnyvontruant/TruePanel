"""Independent-review receipts for AEGIS airworthiness successors.

AEGIS verifies detached signatures through an injected verifier.  It never
holds a private key, signs a receipt, installs an envelope, or grants control
authority.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

ACCEPTANCE_SCHEMA = "truepanel.aegis-acceptance-receipt/v1"
TRUST_POLICY_SCHEMA = "truepanel.aegis-reviewer-trust-policy/v1"
SignatureVerifier = Callable[[str, bytes, str], bool]


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def semantic_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(dict(value))).hexdigest()


def _timestamp(value: Any) -> float | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    result = parsed.astimezone(UTC).timestamp()
    return result if math.isfinite(result) else None


def acceptance_statement(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact semantic statement covered by every signature."""

    return {
        "schema": receipt.get("schema"),
        "receipt_id": receipt.get("receipt_id"),
        "decision": receipt.get("decision"),
        "candidate_envelope_sha256": receipt.get("candidate_envelope_sha256"),
        "appraisal_sha256": receipt.get("appraisal_sha256"),
        "predecessor_envelope_sha256": receipt.get("predecessor_envelope_sha256"),
        "issued_at": receipt.get("issued_at"),
        "expires_at": receipt.get("expires_at"),
        "environment": receipt.get("environment"),
        "promotion_request_sha256": receipt.get("promotion_request_sha256"),
    }


def evaluate_acceptance_receipt(
    *,
    receipt: Mapping[str, Any],
    candidate: Mapping[str, Any],
    appraisal: Mapping[str, Any],
    predecessor: Mapping[str, Any],
    trust_policy: Mapping[str, Any],
    verifier: SignatureVerifier,
    now: float,
) -> dict[str, Any]:
    """Verify quorum and binding without accepting or installing anything."""

    conditions: list[dict[str, Any]] = []

    def add(name: str, passed: bool, reason: str) -> None:
        conditions.append({"condition": name, "passed": bool(passed), "reason": reason})

    add(
        "receipt_schema",
        receipt.get("schema") == ACCEPTANCE_SCHEMA,
        "ReceiptSchemaMatched"
        if receipt.get("schema") == ACCEPTANCE_SCHEMA
        else "ReceiptSchemaInvalid",
    )
    add(
        "trust_policy_schema",
        trust_policy.get("schema") == TRUST_POLICY_SCHEMA,
        "TrustPolicyMatched"
        if trust_policy.get("schema") == TRUST_POLICY_SCHEMA
        else "TrustPolicyInvalid",
    )
    add(
        "review_decision",
        receipt.get("decision") == "ACCEPTED_FOR_OPERATOR_PROMOTION",
        "ReviewAccepted"
        if receipt.get("decision") == "ACCEPTED_FOR_OPERATOR_PROMOTION"
        else "ReviewDecisionInvalid",
    )
    add(
        "candidate_binding",
        receipt.get("candidate_envelope_sha256") == semantic_sha256(candidate),
        "CandidateBound"
        if receipt.get("candidate_envelope_sha256") == semantic_sha256(candidate)
        else "CandidateDigestMismatch",
    )
    add(
        "appraisal_binding",
        receipt.get("appraisal_sha256") == semantic_sha256(appraisal),
        "AppraisalBound"
        if receipt.get("appraisal_sha256") == semantic_sha256(appraisal)
        else "AppraisalDigestMismatch",
    )
    add(
        "predecessor_binding",
        receipt.get("predecessor_envelope_sha256") == semantic_sha256(predecessor),
        "PredecessorBound"
        if receipt.get("predecessor_envelope_sha256") == semantic_sha256(predecessor)
        else "PredecessorDigestMismatch",
    )
    add(
        "appraisal_ready",
        appraisal.get("status") == "READY_FOR_OPERATOR_REVIEW",
        "AppraisalReady"
        if appraisal.get("status") == "READY_FOR_OPERATOR_REVIEW"
        else "AppraisalNotReady",
    )

    issued = _timestamp(receipt.get("issued_at"))
    expires = _timestamp(receipt.get("expires_at"))
    chronology = (
        issued is not None
        and expires is not None
        and issued <= float(now) < expires
        and 0 < expires - issued <= 24 * 60 * 60
    )
    add(
        "receipt_fresh",
        chronology,
        "ReceiptFresh" if chronology else "ReceiptExpiredOrInvalid",
    )

    threshold = trust_policy.get("threshold")
    keys = trust_policy.get("keys")
    policy_valid = (
        isinstance(threshold, int)
        and not isinstance(threshold, bool)
        and threshold >= 2
        and isinstance(keys, Sequence)
        and not isinstance(keys, (str, bytes))
    )
    add(
        "separation_of_duty",
        policy_valid,
        "ThresholdPolicyValid" if policy_valid else "ThresholdPolicyInvalid",
    )
    key_map = {
        str(item.get("key_id")): item
        for item in keys or []
        if isinstance(item, Mapping) and item.get("key_id")
    }
    statement = _canonical(acceptance_statement(receipt))
    valid_reviewers: set[str] = set()
    valid_keys: set[str] = set()
    for signature in receipt.get("signatures") or []:
        if not isinstance(signature, Mapping):
            continue
        key_id = str(signature.get("key_id") or "")
        reviewer = str(signature.get("reviewer_id") or "")
        key = key_map.get(key_id)
        if not key or not reviewer or key.get("reviewer_id") != reviewer:
            continue
        valid_from = _timestamp(key.get("valid_from"))
        valid_until = _timestamp(key.get("valid_until"))
        revoked_at = (
            _timestamp(key.get("revoked_at")) if key.get("revoked_at") else None
        )
        lifecycle_ok = (
            valid_from is not None
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
            valid_reviewers.add(reviewer)
            valid_keys.add(key_id)
    quorum = (
        policy_valid
        and len(valid_reviewers) >= threshold
        and len(valid_keys) >= threshold
    )
    add(
        "independent_signature_quorum",
        quorum,
        "SignatureQuorumMet" if quorum else "SignatureQuorumMissing",
    )

    failed = [item for item in conditions if not item["passed"]]
    status = "ELIGIBLE_FOR_OPERATOR_PROMOTION" if not failed else "HOLD"
    return {
        "schema": ACCEPTANCE_SCHEMA,
        "status": status,
        "reason": "IndependentReviewVerified" if not failed else failed[0]["reason"],
        "conditions": conditions,
        "valid_reviewer_count": len(valid_reviewers),
        "required_reviewer_count": threshold if isinstance(threshold, int) else None,
        "receipt_sha256": semantic_sha256(receipt),
        "candidate_installed": False,
        "automatic_acceptance": False,
        "private_key_material": False,
        "runtime_writes": 0,
        "production_mutation": False,
        "control_authority": False,
    }


__all__ = [
    "ACCEPTANCE_SCHEMA",
    "TRUST_POLICY_SCHEMA",
    "acceptance_statement",
    "evaluate_acceptance_receipt",
    "semantic_sha256",
]
