"""Apply root-governed compromise time to historical reviewer signatures."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from .ssh_verifier import (
    MAX_ALLOWED_SIGNERS_BYTES,
    MAX_SIGNATURE_BYTES,
    validate_allowed_signers_roster,
)
from .temperature_calibration_candidate_appraisal import MAX_PUBLIC_BYTES, _snapshot
from .temperature_reviewer_root_rotation import (
    STATUS_TRUSTED as ROTATION_TRUSTED,
)
from .temperature_reviewer_root_rotation import (
    evaluate_temperature_reviewer_root_rotation,
)
from .temperature_two_person_replay_review import NAMESPACE as REVIEW_NAMESPACE
from .temperature_two_person_replay_review import REVIEWER_KEY_ID, STATEMENT_SCHEMA

SCHEMA: Final = "truepanel.aegis-temperature-reviewer-signature-validity/v1"
STATUS_VALID: Final = "HISTORICAL_REVIEWER_SIGNATURE_VALID"
STATUS_PRECOMPROMISE: Final = "HISTORICAL_SIGNATURE_VALID_BEFORE_COMPROMISE"
STATUS_COMPROMISED: Final = "HOLD_SIGNATURE_AT_OR_AFTER_COMPROMISE"
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
_STATEMENT_KEYS = {
    "schema",
    "namespace",
    "scope",
    "key_id",
    "reviewer_key_fingerprint",
    "prepared_at_utc",
    "expires_at_utc",
    "decision",
    "rationale",
    "primary_review_receipt_sha256",
    "replay_receipt_sha256",
    "primary_operator_key_fingerprint",
    "independent_identity_required",
    "two_person_quorum",
    "manual_calibration_consideration",
    *_DENIED,
}


def _time(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("ReviewerSignatureTimeInvalid")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC:
        raise ValueError("ReviewerSignatureTimeInvalid")
    return parsed


def _reviewer_fingerprint(verifier: Any) -> str:
    if getattr(verifier, "namespace", None) != REVIEW_NAMESPACE or getattr(
        verifier, "expected_key_ids", None
    ) != (REVIEWER_KEY_ID,):
        raise ValueError("ReviewerSignatureVerifierPolicyMismatch")
    path = getattr(verifier, "allowed_signers_path", None)
    if not isinstance(path, Path):
        raise ValueError("ReviewerSignatureVerifierPolicyMismatch")
    return validate_allowed_signers_roster(
        _snapshot(path, MAX_ALLOWED_SIGNERS_BYTES), expected_key_ids=(REVIEWER_KEY_ID,)
    )[REVIEWER_KEY_ID]


def evaluate_temperature_reviewer_signature_validity(
    predecessor_verifier: Any,
    successor_verifier: Any,
    rotation_statement_path: str | Path,
    predecessor_signature_path: str | Path,
    successor_signature_path: str | Path,
    reviewer_verifier: Any,
    review_statement_path: str | Path,
    review_signature_path: str | Path,
    *,
    now_utc: str,
) -> dict[str, Any]:
    errors: list[str] = []
    signature_verified = False
    rotation_verified = False
    compromise_time = revocation_time = None
    disposition = STATUS_HOLD
    decision = None
    try:
        rotation = evaluate_temperature_reviewer_root_rotation(
            predecessor_verifier,
            successor_verifier,
            rotation_statement_path,
            predecessor_signature_path,
            successor_signature_path,
            now_utc=now_utc,
        )
        if rotation["status"] != ROTATION_TRUSTED:
            raise ValueError("ReviewerSignatureRotationNotTrusted")
        rotation_verified = True
        rotation_statement = json.loads(
            _snapshot(Path(rotation_statement_path), MAX_PUBLIC_BYTES)
        )
        payload = _snapshot(Path(review_statement_path), MAX_PUBLIC_BYTES)
        statement = json.loads(payload)
        fingerprint = _reviewer_fingerprint(reviewer_verifier)
        decision = statement.get("decision")
        concurred = decision == "CONCUR_ACCEPT_EVIDENCE"
        if (
            set(statement) != _STATEMENT_KEYS
            or statement.get("schema") != STATEMENT_SCHEMA
            or statement.get("namespace") != REVIEW_NAMESPACE
            or statement.get("scope") != "independent-replay-evidence-concurrence-only"
            or statement.get("key_id") != REVIEWER_KEY_ID
            or decision not in {"CONCUR_ACCEPT_EVIDENCE", "DISSENT_HOLD_EVIDENCE"}
            or statement.get("independent_identity_required") is not True
            or statement.get("two_person_quorum") is not concurred
            or statement.get("manual_calibration_consideration") is not concurred
            or (
                statement.get("rationale")
                == "independently-reconstructed-and-concurred"
            )
            is not concurred
            or statement.get("rationale")
            not in {
                "independently-reconstructed-and-concurred",
                "independent-review-caution",
                "evidence-reconstruction-mismatch",
                "external-review-required",
            }
        ):
            raise ValueError("ReviewerSignatureStatementProfileInvalid")
        if statement.get("reviewer_key_fingerprint") != fingerprint:
            raise ValueError("ReviewerSignatureFingerprintMismatch")
        if any(statement.get(key) is not False for key in _DENIED):
            raise ValueError("ReviewerSignatureAuthorityEscalation")
        signed_at = _time(statement["prepared_at_utc"])
        if _time(statement["expires_at_utc"]) <= signed_at:
            raise ValueError("ReviewerSignatureTimeInvalid")
        if signed_at > _time(now_utc):
            raise ValueError("ReviewerSignatureFromFuture")
        signature = _snapshot(Path(review_signature_path), MAX_SIGNATURE_BYTES).decode(
            "ascii"
        )
        signature_verified = (
            reviewer_verifier(REVIEWER_KEY_ID, payload, signature) is True
        )
        if not signature_verified:
            raise ValueError("ReviewerSignatureNotAuthenticated")
        matching = [
            event
            for event in rotation_statement["compromise_events"]
            if event.get("fingerprint") == fingerprint
        ]
        if len(matching) > 1:
            raise ValueError("ReviewerSignatureCompromiseHistoryAmbiguous")
        if matching:
            event = matching[0]
            compromised, revoked = (
                _time(event["compromised_at_utc"]),
                _time(event["revoked_at_utc"]),
            )
            if compromised > revoked:
                raise ValueError("ReviewerSignatureCompromiseTimelineInvalid")
            compromise_time, revocation_time = (
                event["compromised_at_utc"],
                event["revoked_at_utc"],
            )
            disposition = (
                STATUS_PRECOMPROMISE if signed_at < compromised else STATUS_COMPROMISED
            )
        else:
            disposition = STATUS_VALID
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        KeyError,
        OSError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as error:
        errors.append(str(error) or error.__class__.__name__)
    accepted = not errors and disposition in {STATUS_VALID, STATUS_PRECOMPROMISE}
    return {
        "schema": SCHEMA,
        "status": disposition if not errors else STATUS_HOLD,
        "reviewer_signature_verified": signature_verified,
        "root_rotation_verified": rotation_verified,
        "compromise_at_utc": compromise_time,
        "revoked_at_utc": revocation_time,
        "historical_signature_accepted": accepted,
        "eligible_for_reviewer_quorum": accepted
        and decision == "CONCUR_ACCEPT_EVIDENCE",
        **{key: False for key in _DENIED},
        "errors": errors,
    }


def pending_temperature_reviewer_signature_validity(
    rotation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": "ACTION_REQUIRED_HISTORICAL_SIGNATURE_VALIDITY"
        if rotation.get("dual_control_verified") is True
        else STATUS_HOLD,
        "reviewer_signature_verified": False,
        "root_rotation_verified": False,
        "compromise_at_utc": None,
        "revoked_at_utc": None,
        "historical_signature_accepted": False,
        "eligible_for_reviewer_quorum": False,
        **{key: False for key in _DENIED},
        "next_action": "Revalidate the exact reviewer signature against the dual-signed compromise timeline before it can count toward quorum.",
    }


__all__ = [
    "STATUS_COMPROMISED",
    "STATUS_PRECOMPROMISE",
    "STATUS_VALID",
    "evaluate_temperature_reviewer_signature_validity",
    "pending_temperature_reviewer_signature_validity",
]
