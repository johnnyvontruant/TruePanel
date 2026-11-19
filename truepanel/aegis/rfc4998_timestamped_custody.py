"""Independent RFC 3161 signing-time gate for authenticated custody."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Final

from .rfc4998_authenticated_custody import (
    SCHEMA as AUTHENTICATED_CUSTODY_SCHEMA,
)
from .rfc4998_authenticated_custody import STATUS_AUTHENTICATED

SCHEMA: Final = "truepanel.aegis-rfc4998-timestamped-custody/v1"
STATUS_TIMESTAMPED: Final = "RFC3161_CUSTODY_TIME_REHEARSED"
STATUS_TIMESTAMP_REQUIRED: Final = "ACTION_REQUIRED_RFC3161_CUSTODY_TIMESTAMP"
STATUS_HOLD: Final = "HOLD"

_DENIED: Final = (
    "production_trusted",
    "runtime_authority",
    "deployment_authority",
    "hardware_authority",
    "network_authority",
    "storage_authority",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _timestamp(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{name}Invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError(f"{name}Invalid") from error
    return parsed.astimezone(UTC)


def evaluate_timestamped_custody(
    authenticated_custody: Mapping[str, Any],
    signature: str | None,
    timestamp_token: bytes | None,
    timestamp_verifier: Callable[[bytes, bytes], Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Countersign exact custody-signature bytes without granting authority."""

    errors: list[str] = []
    signature_bytes = b""
    timestamp: Mapping[str, Any] = {}
    if authenticated_custody.get("schema") != AUTHENTICATED_CUSTODY_SCHEMA:
        errors.append("AuthenticatedCustodySchemaUnsupported")
    if authenticated_custody.get("status") != STATUS_AUTHENTICATED:
        errors.append("AuthenticatedCustodyRequired")
    if authenticated_custody.get("custodian_signature_verified") is not True:
        errors.append("CustodianSignatureNotVerified")
    if authenticated_custody.get("dual_oracle_receipt_verified") is not True:
        errors.append("DualOracleReceiptNotVerified")
    if any(authenticated_custody.get(name) is not False for name in _DENIED):
        errors.append("AuthenticatedCustodyAuthorityEscalation")
    try:
        if signature is None:
            errors.append("CustodianSignatureMissing")
        else:
            signature_bytes = signature.encode("ascii", errors="strict")
            if not signature_bytes:
                raise ValueError("CustodianSignatureEmpty")
    except (UnicodeError, ValueError) as error:
        errors.append(str(error))
    if timestamp_token is not None and (
        not isinstance(timestamp_token, bytes) or not timestamp_token
    ):
        errors.append("CustodyTimestampTokenInvalid")

    if not errors and timestamp_token is not None and timestamp_verifier is not None:
        try:
            candidate = timestamp_verifier(signature_bytes, timestamp_token)
            timestamp = candidate if isinstance(candidate, Mapping) else {}
        except (OSError, RuntimeError, TypeError, ValueError):
            timestamp = {}
        if timestamp.get("verified") is not True:
            errors.append("CustodyTimestampInvalid")
        if timestamp.get("profile") != "RFC3161":
            errors.append("CustodyTimestampProfileInvalid")
        if not isinstance(timestamp.get("policy_oid"), str):
            errors.append("CustodyTimestampPolicyMissing")
        if timestamp.get("hash_algorithm") not in {"sha256", "sha512"}:
            errors.append("CustodyTimestampDigestInvalid")
        try:
            generated = _timestamp(timestamp.get("gen_time_utc"), "TimestampTime")
            issued = _timestamp(authenticated_custody.get("issued_at"), "IssuedAt")
            expires = _timestamp(authenticated_custody.get("expires_at"), "ExpiresAt")
            if generated < issued:
                errors.append("CustodyTimestampBeforeValidity")
            if generated > expires:
                errors.append("CustodyTimestampAfterValidity")
        except ValueError as error:
            errors.append(str(error))
    elif not errors and timestamp_token is not None:
        errors.append("CustodyTimestampVerifierUnavailable")

    if errors:
        status = STATUS_HOLD
    elif timestamp_token is None:
        status = STATUS_TIMESTAMP_REQUIRED
    elif timestamp_verifier is None:
        status = STATUS_HOLD
        errors.append("CustodyTimestampVerifierUnavailable")
    else:
        status = STATUS_TIMESTAMPED

    result = {
        "schema": SCHEMA,
        "status": status,
        "record_id": authenticated_custody.get("record_id"),
        "custody_id": authenticated_custody.get("custody_id"),
        "custodian_id": authenticated_custody.get("custodian_id"),
        "authenticated_custody_record_sha256": authenticated_custody.get(
            "record_sha256"
        ),
        "custodian_signature_sha256": (
            hashlib.sha256(signature_bytes).hexdigest() if signature_bytes else None
        ),
        "timestamp_token_sha256": (
            hashlib.sha256(timestamp_token).hexdigest()
            if isinstance(timestamp_token, bytes) and timestamp_token
            else None
        ),
        "timestamp_profile": timestamp.get("profile"),
        "timestamp_policy_oid": timestamp.get("policy_oid"),
        "timestamp_hash_algorithm": timestamp.get("hash_algorithm"),
        "timestamp_gen_time_utc": timestamp.get("gen_time_utc"),
        "signature_countersigned": status == STATUS_TIMESTAMPED,
        "independent_signing_time_rehearsed": status == STATUS_TIMESTAMPED,
        "active_runtime_record_validation": "PENDING",
        "eligible_for_production_trust": False,
        "errors": list(dict.fromkeys(errors)),
        **{name: False for name in _DENIED},
    }
    result["record_sha256"] = hashlib.sha256(_canonical(result)).hexdigest()
    return result


__all__ = [
    "SCHEMA",
    "STATUS_HOLD",
    "STATUS_TIMESTAMPED",
    "STATUS_TIMESTAMP_REQUIRED",
    "evaluate_timestamped_custody",
]
