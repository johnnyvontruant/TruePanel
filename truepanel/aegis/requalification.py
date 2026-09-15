"""Fail-closed review gate for successor AIRWORTHINESS envelopes."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .assurance import evaluate_airworthiness

REQUALIFICATION_SCHEMA = "truepanel.aegis-requalification/v1"
MAX_VALIDITY_SECONDS = 92 * 24 * 60 * 60
_STABLE_RELEASE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?$")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def envelope_sha256(envelope: Mapping[str, Any]) -> str:
    """Digest an envelope's semantic content, independent of file layout."""

    return hashlib.sha256(_canonical(dict(envelope))).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def renewal_contract_sha256(package_root: Path | None = None) -> str:
    root = package_root or Path(__file__).resolve().parents[1]
    return _sha256_file(root / "aegis/requalification.py")


def _timestamp(value: Any) -> float | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    result = parsed.astimezone(UTC).timestamp()
    return result if math.isfinite(result) else None


def _release(value: Any) -> tuple[int, int, int] | None:
    matched = _STABLE_RELEASE.fullmatch(str(value or ""))
    if not matched:
        return None
    return tuple(int(item or 0) for item in matched.groups())


def classify_platform_transition(current: Any, candidate: Any) -> str:
    """Classify stable release movement without guessing prerelease order."""

    before = _release(current)
    after = _release(candidate)
    if before is None or after is None:
        return "UNSUPPORTED"
    if after == before:
        return "SAME"
    return "UPGRADE" if after > before else "DOWNGRADE"


def renewal_guidance(airworthiness: Mapping[str, Any]) -> dict[str, Any]:
    """Return actionable, non-authoritative guidance for the assurance state."""

    status = str(airworthiness.get("status") or "HOLD").upper()
    reason = str(airworthiness.get("reason") or "EnvelopeUnavailable")
    if status == "CURRENT":
        state = "MONITOR"
        next_action = "Preserve evidence and review before the envelope expires."
    elif status == "REVIEW":
        state = "COLLECT_FRESH_EVIDENCE"
        next_action = "Collect a fresh governed platform witness, then re-evaluate."
    elif reason == "PlatformDrift":
        state = "REQUALIFICATION_REQUIRED"
        next_action = (
            "Keep the old envelope on HOLD; rehearse and independently review a "
            "successor for the observed platform."
        )
    else:
        state = "REVALIDATION_REQUIRED"
        next_action = (
            "Identify the failed condition and reproduce its acceptance evidence "
            "before proposing a successor."
        )
    return {
        "schema": REQUALIFICATION_SCHEMA,
        "state": state,
        "reason": reason,
        "next_action": next_action,
        "completion_criteria": [
            "successor names the exact predecessor digest",
            "current runtime, policy, coverage, and platform evidence all match",
            "validity is bounded and downgrade protection passes",
            "an operator reviews the proposal outside AEGIS",
        ],
        "abort_conditions": [
            "predecessor lineage is missing or ambiguous",
            "platform movement is a downgrade or cannot be ordered safely",
            "any bound subject, policy, coverage, or witness differs",
            "the proposal attempts automatic acceptance",
        ],
        "automatic_acceptance": False,
        "production_mutation": False,
        "control_authority": False,
    }


def evaluate_successor_envelope(
    *,
    accepted: Mapping[str, Any],
    candidate: Mapping[str, Any],
    payload: Mapping[str, Any],
    coverage_matrix: Mapping[str, Any],
    correlation_policy: Mapping[str, Any],
    now: float,
    package_root: Path | None = None,
) -> dict[str, Any]:
    """Appraise a candidate without installing, accepting, or writing it."""

    root = package_root or Path(__file__).resolve().parents[1]
    conditions: list[dict[str, Any]] = []

    def condition(name: str, passed: bool, reason: str) -> None:
        conditions.append({"condition": name, "passed": passed, "reason": reason})

    predecessor = str(candidate.get("predecessor_envelope_sha256") or "")
    condition(
        "predecessor_lineage",
        predecessor == envelope_sha256(accepted),
        "PredecessorMatched" if predecessor == envelope_sha256(accepted) else "PredecessorMismatch",
    )
    unique_id = bool(candidate.get("envelope_id")) and candidate.get(
        "envelope_id"
    ) != accepted.get("envelope_id")
    condition("successor_identity", unique_id, "SuccessorIdentified" if unique_id else "EnvelopeIdentityReused")

    issued = _timestamp(candidate.get("issued_at"))
    expires = _timestamp(candidate.get("expires_at"))
    accepted_issued = _timestamp(accepted.get("issued_at"))
    chronology = (
        issued is not None
        and expires is not None
        and accepted_issued is not None
        and accepted_issued <= issued <= float(now) < expires
        and 0 < expires - issued <= MAX_VALIDITY_SECONDS
    )
    condition("bounded_chronology", chronology, "ValidityBounded" if chronology else "ValidityWindowInvalid")

    transition = classify_platform_transition(
        accepted.get("platform_version"), candidate.get("platform_version")
    )
    transition_supported = transition in {"SAME", "UPGRADE"}
    condition(
        "platform_transition",
        transition_supported,
        f"Platform{transition.title()}",
    )
    condition(
        "manual_acceptance",
        candidate.get("review_required") is True
        and candidate.get("automatic_acceptance") is False,
        "OperatorReviewRequired"
        if candidate.get("review_required") is True
        and candidate.get("automatic_acceptance") is False
        else "AutomaticAcceptanceForbidden",
    )
    expected_contract = str(candidate.get("renewal_contract_sha256") or "")
    try:
        observed_contract = renewal_contract_sha256(root)
    except OSError:
        observed_contract = ""
    condition(
        "renewal_contract_integrity",
        expected_contract == observed_contract,
        "RenewalContractMatched"
        if expected_contract == observed_contract
        else "RenewalContractDrift",
    )

    appraisal = evaluate_airworthiness(
        payload=payload,
        coverage_matrix=coverage_matrix,
        correlation_policy=correlation_policy,
        now=now,
        envelope=candidate,
        package_root=root,
    )
    condition(
        "candidate_airworthiness",
        appraisal.get("status") == "CURRENT",
        str(appraisal.get("reason") or "CandidateUnavailable"),
    )

    failed = [item for item in conditions if item["passed"] is not True]
    unsupported = transition == "UNSUPPORTED"
    candidate_only_review = (
        appraisal.get("status") == "REVIEW"
        and len(failed) == 1
        and failed[0]["condition"] == "candidate_airworthiness"
    )
    if candidate_only_review:
        status = "REVIEW"
        reason = str(appraisal.get("reason") or "CandidateEvidenceIncomplete")
    elif unsupported and all(
        item["passed"] for item in conditions if item["condition"] != "platform_transition"
    ):
        status = "REVIEW"
        reason = "PlatformOrderingRequiresReview"
    elif failed:
        status = "HOLD"
        reason = failed[0]["reason"]
    else:
        status = "READY_FOR_OPERATOR_REVIEW"
        reason = "SuccessorEvidenceComplete"

    return {
        "schema": REQUALIFICATION_SCHEMA,
        "status": status,
        "reason": reason,
        "transition": transition,
        "predecessor_envelope_id": accepted.get("envelope_id"),
        "candidate_envelope_id": candidate.get("envelope_id"),
        "conditions": conditions,
        "candidate_appraisal": {
            "status": appraisal.get("status"),
            "reason": appraisal.get("reason"),
        },
        "review_required": True,
        "automatic_acceptance": False,
        "candidate_installed": False,
        "runtime_writes": 0,
        "production_mutation": False,
        "control_authority": False,
    }


__all__ = [
    "REQUALIFICATION_SCHEMA",
    "classify_platform_transition",
    "envelope_sha256",
    "evaluate_successor_envelope",
    "renewal_contract_sha256",
    "renewal_guidance",
]
