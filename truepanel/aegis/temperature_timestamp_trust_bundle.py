"""Govern independently operated RFC 3161 timestamp authorities."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

SCHEMA: Final = "truepanel.aegis-temperature-timestamp-trust-bundle/v1"
STATUS_TRUSTED: Final = "GOVERNED_TIMESTAMP_THRESHOLD_SATISFIED"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_GOVERNED_TIMESTAMP_THRESHOLD"
STATUS_HOLD: Final = "HOLD"
_DENIED = (
    "field_validated",
    "production_validated",
    "candidate_accepted",
    "candidate_installed",
    "capture_authority",
    "runtime_authority",
    "deployment_authority",
    "hardware_authority",
    "storage_write_authority",
    "network_authority",
    "automatic_promotion",
)


def _time(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("TimestampTrustTimeInvalid")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC:
        raise ValueError("TimestampTrustTimeInvalid")
    return parsed


def evaluate_timestamp_trust_bundle(
    bundle: dict[str, Any], witnesses: list[dict[str, Any]], *, now_utc: str
) -> dict[str, Any]:
    """Count verified witnesses by distinct governed operator, never by token."""
    errors: list[str] = []
    accepted: list[str] = []
    generation = threshold = None
    try:
        if bundle.get("schema") != SCHEMA or set(bundle) != {
            "schema",
            "generation",
            "threshold",
            "valid_from_utc",
            "valid_until_utc",
            "authorities",
            "deployment_authority",
            "hardware_authority",
        }:
            raise ValueError("TimestampTrustBundleProfileInvalid")
        generation, threshold = bundle["generation"], bundle["threshold"]
        if not isinstance(generation, int) or generation < 1:
            raise ValueError("TimestampTrustGenerationInvalid")
        if not isinstance(threshold, int) or threshold < 2:
            raise ValueError("TimestampTrustThresholdInvalid")
        if (
            bundle["deployment_authority"] is not False
            or bundle["hardware_authority"] is not False
        ):
            raise ValueError("TimestampTrustAuthorityEscalation")
        now = _time(now_utc)
        if not (
            _time(bundle["valid_from_utc"]) <= now < _time(bundle["valid_until_utc"])
        ):
            raise ValueError("TimestampTrustBundleExpired")
        authorities = bundle["authorities"]
        if not isinstance(authorities, list) or len(authorities) < threshold:
            raise ValueError("TimestampTrustAuthoritiesInsufficient")
        governed: dict[tuple[str, str], dict[str, Any]] = {}
        operators: set[str] = set()
        for authority in authorities:
            required = {
                "operator",
                "root_fingerprint",
                "policy_oid",
                "valid_from_utc",
                "valid_until_utc",
            }
            if not isinstance(authority, dict) or set(authority) != required:
                raise ValueError("TimestampTrustAuthorityProfileInvalid")
            operator = authority["operator"]
            if not isinstance(operator, str) or not operator or operator in operators:
                raise ValueError("TimestampTrustOperatorDuplicate")
            operators.add(operator)
            governed[(operator, authority["root_fingerprint"])] = authority
        for witness in witnesses:
            if (
                witness.get("verified") is not True
                or witness.get("profile") != "RFC3161"
            ):
                continue
            key = (witness.get("operator"), witness.get("root_fingerprint"))
            authority = governed.get(key)
            if (
                authority is None
                or witness.get("policy_oid") != authority["policy_oid"]
            ):
                continue
            witnessed = _time(witness["gen_time_utc"])
            if (
                _time(authority["valid_from_utc"])
                <= witnessed
                < _time(authority["valid_until_utc"])
            ):
                accepted.append(key[0])
        accepted = sorted(set(accepted))
        if len(accepted) < threshold:
            raise ValueError("TimestampTrustThresholdNotMet")
    except (KeyError, TypeError, ValueError) as error:
        errors.append(str(error) or error.__class__.__name__)
    trusted = not errors
    return {
        "schema": SCHEMA,
        "status": STATUS_TRUSTED if trusted else STATUS_HOLD,
        "generation": generation,
        "threshold": threshold,
        "distinct_operators_verified": len(accepted),
        "verified_operators": accepted,
        "timestamp_trust_bundle_verified": trusted,
        "eligible_for_reviewer_quorum": trusted,
        **{key: False for key in _DENIED},
        "errors": errors,
    }


def pending_timestamp_trust_bundle(witness: dict[str, Any]) -> dict[str, Any]:
    ready = witness.get("timestamp_witness_verified") is True
    return {
        "schema": SCHEMA,
        "status": STATUS_REQUIRED if ready else STATUS_HOLD,
        "generation": None,
        "threshold": 2,
        "distinct_operators_verified": 0,
        "verified_operators": [],
        "timestamp_trust_bundle_verified": False,
        "eligible_for_reviewer_quorum": False,
        **{key: False for key in _DENIED},
        "next_action": "Verify timestamps from at least two governed independent operators within their exact validity intervals.",
    }


__all__ = [
    "SCHEMA",
    "evaluate_timestamp_trust_bundle",
    "pending_timestamp_trust_bundle",
]
