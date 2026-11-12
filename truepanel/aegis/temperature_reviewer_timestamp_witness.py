"""Require independently witnessed time for historical reviewer signatures."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from .rfc3161_timestamp import MAX_TIMESTAMP_TOKEN_BYTES
from .temperature_calibration_candidate_appraisal import MAX_PUBLIC_BYTES, _snapshot
from .temperature_reviewer_signature_validity import (
    evaluate_temperature_reviewer_signature_validity,
)

SCHEMA: Final = "truepanel.aegis-temperature-reviewer-timestamp-witness/v1"
STATUS_VALID: Final = "RFC3161_WITNESSED_REVIEWER_SIGNATURE_VALID"
STATUS_PRECOMPROMISE: Final = "RFC3161_WITNESSED_SIGNATURE_VALID_BEFORE_COMPROMISE"
STATUS_COMPROMISED: Final = "HOLD_WITNESSED_SIGNATURE_AT_OR_AFTER_COMPROMISE"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_RFC3161_TIMESTAMP_WITNESS"
STATUS_HOLD: Final = "HOLD"
MAX_WITNESS_DELAY: Final = timedelta(minutes=15)
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
        raise ValueError("ReviewerTimestampWitnessTimeInvalid")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC:
        raise ValueError("ReviewerTimestampWitnessTimeInvalid")
    return parsed


def evaluate_temperature_reviewer_timestamp_witness(
    predecessor_verifier: Any,
    successor_verifier: Any,
    rotation_statement_path: str | Path,
    predecessor_signature_path: str | Path,
    successor_signature_path: str | Path,
    reviewer_verifier: Any,
    review_statement_path: str | Path,
    review_signature_path: str | Path,
    timestamp_verifier: Any,
    timestamp_token_path: str | Path,
    *,
    now_utc: str,
) -> dict[str, Any]:
    base = evaluate_temperature_reviewer_signature_validity(
        predecessor_verifier,
        successor_verifier,
        rotation_statement_path,
        predecessor_signature_path,
        successor_signature_path,
        reviewer_verifier,
        review_statement_path,
        review_signature_path,
        now_utc=now_utc,
    )
    errors: list[str] = []
    timestamp_verified = False
    witnessed_at = policy_oid = hash_algorithm = None
    status = STATUS_HOLD
    try:
        if (
            base["root_rotation_verified"] is not True
            or base["reviewer_signature_verified"] is not True
            or base["errors"]
        ):
            raise ValueError("ReviewerTimestampWitnessPrerequisiteInvalid")
        signature = _snapshot(Path(review_signature_path), MAX_PUBLIC_BYTES)
        token = _snapshot(Path(timestamp_token_path), MAX_TIMESTAMP_TOKEN_BYTES)
        witness = timestamp_verifier(signature, token)
        if (
            not isinstance(witness, dict)
            or witness.get("verified") is not True
            or witness.get("profile") != "RFC3161"
        ):
            raise ValueError("ReviewerTimestampWitnessNotVerified")
        timestamp_verified = True
        witnessed_at = witness["gen_time_utc"]
        policy_oid = witness["policy_oid"]
        hash_algorithm = witness["hash_algorithm"]
        witnessed = _time(witnessed_at)
        statement = json.loads(_snapshot(Path(review_statement_path), MAX_PUBLIC_BYTES))
        prepared, now = _time(statement["prepared_at_utc"]), _time(now_utc)
        if witnessed < prepared:
            raise ValueError("ReviewerTimestampWitnessPredatesStatement")
        if witnessed - prepared > MAX_WITNESS_DELAY:
            raise ValueError("ReviewerTimestampWitnessDelayExceeded")
        if witnessed > now:
            raise ValueError("ReviewerTimestampWitnessFromFuture")
        if base["compromise_at_utc"] is None:
            status = STATUS_VALID
        elif witnessed < _time(base["compromise_at_utc"]):
            status = STATUS_PRECOMPROMISE
        else:
            status = STATUS_COMPROMISED
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        errors.append(str(error) or error.__class__.__name__)
    accepted = not errors and status in {STATUS_VALID, STATUS_PRECOMPROMISE}
    return {
        "schema": SCHEMA,
        "status": status if not errors else STATUS_HOLD,
        "reviewer_signature_verified": base["reviewer_signature_verified"],
        "root_rotation_verified": base["root_rotation_verified"],
        "timestamp_witness_verified": timestamp_verified,
        "timestamp_profile": "RFC3161" if timestamp_verified else None,
        "timestamp_policy_oid": policy_oid,
        "timestamp_hash_algorithm": hash_algorithm,
        "witnessed_at_utc": witnessed_at,
        "compromise_at_utc": base["compromise_at_utc"],
        "revoked_at_utc": base["revoked_at_utc"],
        "historical_signature_accepted": accepted,
        "eligible_for_reviewer_quorum": accepted
        and base["eligible_for_reviewer_quorum"],
        **{key: False for key in _DENIED},
        "errors": errors,
    }


def pending_temperature_reviewer_timestamp_witness(
    signature_validity: dict[str, Any],
) -> dict[str, Any]:
    ready = (
        signature_validity.get("root_rotation_verified") is True
        and signature_validity.get("reviewer_signature_verified") is True
    )
    return {
        "schema": SCHEMA,
        "status": STATUS_REQUIRED if ready else STATUS_HOLD,
        "reviewer_signature_verified": False,
        "root_rotation_verified": False,
        "timestamp_witness_verified": False,
        "timestamp_profile": None,
        "timestamp_policy_oid": None,
        "timestamp_hash_algorithm": None,
        "witnessed_at_utc": None,
        "compromise_at_utc": None,
        "revoked_at_utc": None,
        "historical_signature_accepted": False,
        "eligible_for_reviewer_quorum": False,
        **{key: False for key in _DENIED},
        "next_action": "Obtain and verify an RFC 3161 countersignature over the exact reviewer SSHSIG before it can count toward quorum.",
    }


__all__ = [
    "STATUS_COMPROMISED",
    "STATUS_PRECOMPROMISE",
    "STATUS_VALID",
    "evaluate_temperature_reviewer_timestamp_witness",
    "pending_temperature_reviewer_timestamp_witness",
]
