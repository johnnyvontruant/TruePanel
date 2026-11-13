"""Dual-root rotation for governed timestamp trust bundles."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from .ssh_verifier import (
    MAX_ALLOWED_SIGNERS_BYTES,
    MAX_SIGNATURE_BYTES,
    validate_allowed_signers_roster,
)
from .temperature_calibration_candidate_appraisal import (
    MAX_PUBLIC_BYTES,
    _canonical,
    _snapshot,
)
from .temperature_timestamp_trust_bundle import SCHEMA as BUNDLE_SCHEMA

SCHEMA: Final = "truepanel.aegis-temperature-timestamp-trust-rotation/v1"
STATEMENT_SCHEMA: Final = f"{SCHEMA}-statement"
NAMESPACE: Final = "truepanel-aegis-timestamp-trust-rotation-v1@truepanel"
PREDECESSOR_KEY_ID: Final = "timestamp-trust-root-predecessor"
SUCCESSOR_KEY_ID: Final = "timestamp-trust-root-successor"
STATUS_TRUSTED: Final = "TIMESTAMP_TRUST_ROTATION_TRUSTED"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_TIMESTAMP_TRUST_ROTATION"
STATUS_HOLD: Final = "HOLD"
MAX_WINDOW: Final = timedelta(hours=2)
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
        raise ValueError("TimestampTrustRotationTimeInvalid")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC:
        raise ValueError("TimestampTrustRotationTimeInvalid")
    return parsed


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _fingerprint(verifier: Any, key_id: str) -> str:
    if getattr(verifier, "namespace", None) != NAMESPACE or getattr(
        verifier, "expected_key_ids", None
    ) != (key_id,):
        raise ValueError("TimestampTrustRotationVerifierPolicyMismatch")
    path = getattr(verifier, "allowed_signers_path", None)
    if not isinstance(path, Path):
        raise ValueError("TimestampTrustRotationVerifierPolicyMismatch")
    return validate_allowed_signers_roster(
        _snapshot(path, MAX_ALLOWED_SIGNERS_BYTES), expected_key_ids=(key_id,)
    )[key_id]


def build_timestamp_trust_rotation_statement(
    predecessor_verifier: Any,
    successor_verifier: Any,
    previous_bundle: dict[str, Any],
    successor_bundle: dict[str, Any],
    revocation_evidence: tuple[dict[str, str], ...],
    *,
    prepared_at_utc: str,
    expires_at_utc: str,
) -> bytes:
    start, end = _time(prepared_at_utc), _time(expires_at_utc)
    if end <= start or end - start > MAX_WINDOW:
        raise ValueError("TimestampTrustRotationWindowInvalid")
    if (
        previous_bundle.get("schema") != BUNDLE_SCHEMA
        or successor_bundle.get("schema") != BUNDLE_SCHEMA
    ):
        raise ValueError("TimestampTrustRotationBundleProfileInvalid")
    if successor_bundle.get("generation") != previous_bundle.get("generation", 0) + 1:
        raise ValueError("TimestampTrustRotationGenerationInvalid")
    previous_operators = {
        item.get("operator") for item in previous_bundle.get("authorities", [])
    }
    archived: list[dict[str, str]] = []
    seen: set[str] = set()
    for evidence in revocation_evidence:
        if set(evidence) != {
            "operator",
            "type",
            "sha256",
            "produced_at_utc",
            "valid_until_utc",
        }:
            raise ValueError("TimestampTrustRevocationEvidenceProfileInvalid")
        operator = evidence["operator"]
        if operator in seen or operator not in previous_operators:
            raise ValueError("TimestampTrustRevocationEvidenceOperatorInvalid")
        if evidence["type"] not in {"CRL", "OCSP"} or len(evidence["sha256"]) != 64:
            raise ValueError("TimestampTrustRevocationEvidenceInvalid")
        if (
            _time(evidence["produced_at_utc"]) > start
            or _time(evidence["valid_until_utc"]) < start
        ):
            raise ValueError("TimestampTrustRevocationEvidenceStale")
        seen.add(operator)
        archived.append(dict(evidence))
    if seen != previous_operators or not seen:
        raise ValueError("TimestampTrustRevocationEvidenceIncomplete")
    predecessor = _fingerprint(predecessor_verifier, PREDECESSOR_KEY_ID)
    successor = _fingerprint(successor_verifier, SUCCESSOR_KEY_ID)
    if predecessor == successor:
        raise ValueError("TimestampTrustRotationIdentityNotDistinct")
    body = {
        "schema": STATEMENT_SCHEMA,
        "namespace": NAMESPACE,
        "scope": "timestamp-trust-bundle-rotation-only",
        "from_generation": previous_bundle["generation"],
        "to_generation": successor_bundle["generation"],
        "previous_bundle_sha256": _sha(previous_bundle),
        "successor_bundle_sha256": _sha(successor_bundle),
        "predecessor_root_fingerprint": predecessor,
        "successor_root_fingerprint": successor,
        "prepared_at_utc": prepared_at_utc,
        "expires_at_utc": expires_at_utc,
        "revocation_evidence": sorted(archived, key=lambda item: item["operator"]),
        "predecessor_signature_required": True,
        "successor_signature_required": True,
        "automatic_rotation": False,
        **{key: False for key in _DENIED},
    }
    body["statement_sha256"] = _sha(body)
    return _canonical(body)


def evaluate_timestamp_trust_rotation(
    predecessor_verifier: Any,
    successor_verifier: Any,
    previous_bundle: dict[str, Any],
    successor_bundle: dict[str, Any],
    statement_path: str | Path,
    predecessor_signature_path: str | Path,
    successor_signature_path: str | Path,
    *,
    now_utc: str,
) -> dict[str, Any]:
    errors: list[str] = []
    old_verified = new_verified = False
    generation = evidence_count = None
    try:
        payload = _snapshot(Path(statement_path), MAX_PUBLIC_BYTES)
        statement = json.loads(payload)
        expected = build_timestamp_trust_rotation_statement(
            predecessor_verifier,
            successor_verifier,
            previous_bundle,
            successor_bundle,
            tuple(statement["revocation_evidence"]),
            prepared_at_utc=statement["prepared_at_utc"],
            expires_at_utc=statement["expires_at_utc"],
        )
        if payload != expected:
            raise ValueError("TimestampTrustRotationStatementMismatch")
        if not (
            _time(statement["prepared_at_utc"])
            <= _time(now_utc)
            < _time(statement["expires_at_utc"])
        ):
            raise ValueError("TimestampTrustRotationNotActive")
        if (
            not Path(predecessor_signature_path).exists()
            or not Path(successor_signature_path).exists()
        ):
            raise ValueError("TimestampTrustRotationDualSignatureRequired")
        old_signature = _snapshot(
            Path(predecessor_signature_path), MAX_SIGNATURE_BYTES
        ).decode("ascii")
        new_signature = _snapshot(
            Path(successor_signature_path), MAX_SIGNATURE_BYTES
        ).decode("ascii")
        old_verified = (
            predecessor_verifier(PREDECESSOR_KEY_ID, payload, old_signature) is True
        )
        new_verified = (
            successor_verifier(SUCCESSOR_KEY_ID, payload, new_signature) is True
        )
        if not old_verified or not new_verified:
            raise ValueError("TimestampTrustRotationDualSignatureRequired")
        generation = statement["to_generation"]
        evidence_count = len(statement["revocation_evidence"])
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
    trusted = not errors
    return {
        "schema": SCHEMA,
        "status": STATUS_TRUSTED if trusted else STATUS_HOLD,
        "predecessor_signature_verified": old_verified,
        "successor_signature_verified": new_verified,
        "dual_control_verified": trusted,
        "to_generation": generation,
        "revocation_evidence_verified": evidence_count or 0,
        "rotation_authorized": trusted,
        **{key: False for key in _DENIED},
        "errors": errors,
    }


def pending_timestamp_trust_rotation(bundle: dict[str, Any]) -> dict[str, Any]:
    ready = bundle.get("timestamp_trust_bundle_verified") is True
    return {
        "schema": SCHEMA,
        "status": STATUS_REQUIRED if ready else STATUS_HOLD,
        "predecessor_signature_verified": False,
        "successor_signature_verified": False,
        "dual_control_verified": False,
        "to_generation": None,
        "revocation_evidence_verified": 0,
        "rotation_authorized": False,
        **{key: False for key in _DENIED},
        "next_action": "Dual-sign the consecutive timestamp trust bundle and bind current CRL or OCSP evidence for every outgoing operator.",
    }


__all__ = [
    "NAMESPACE",
    "PREDECESSOR_KEY_ID",
    "SUCCESSOR_KEY_ID",
    "STATUS_TRUSTED",
    "build_timestamp_trust_rotation_statement",
    "evaluate_timestamp_trust_rotation",
    "pending_timestamp_trust_rotation",
]
