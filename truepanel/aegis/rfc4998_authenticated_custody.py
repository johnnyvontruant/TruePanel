"""Offline-authenticated custody gate for rehearsed RFC 4998 receipts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Final

from .rfc4998_active_receipt import SCHEMA as ACTIVE_RECEIPT_SCHEMA
from .rfc4998_active_receipt import STATUS_REHEARSED

SCHEMA: Final = "truepanel.aegis-rfc4998-authenticated-custody/v1"
STATEMENT_SCHEMA: Final = "truepanel.aegis-rfc4998-custody-statement/v1"
CUSTODY_SCHEMA: Final = "truepanel.aegis-rfc4998-custody-event/v1"
NAMESPACE: Final = "truepanel-aegis-rfc4998-custody-v1@truepanel"
KEY_ID: Final = "aegis-preservation-custodian"
STATUS_AUTHENTICATED: Final = "AUTHENTICATED_CUSTODY_REHEARSED"
STATUS_SIGNATURE_REQUIRED: Final = "CUSTODY_SIGNATURE_REQUIRED"
STATUS_HOLD: Final = "HOLD"
MAX_VALIDITY_SECONDS: Final = 15 * 60

_DENIED: Final = (
    "production_trusted",
    "runtime_authority",
    "deployment_authority",
    "hardware_authority",
    "network_authority",
    "storage_authority",
)
_RECEIPT_DENIED: Final = (
    "production_trusted",
    "deployment_authority",
    "hardware_authority",
    "network_authority",
    "storage_authority",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _timestamp(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{name}Invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError(f"{name}Invalid") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{name}Invalid")
    return parsed.astimezone(UTC)


def _validate_inputs(
    manifest: Mapping[str, Any],
    active_receipt: Mapping[str, Any],
    custody: Mapping[str, Any],
    *,
    now_utc: str,
) -> tuple[datetime, datetime]:
    if active_receipt.get("schema") != ACTIVE_RECEIPT_SCHEMA:
        raise ValueError("ActiveReceiptSchemaUnsupported")
    if active_receipt.get("active_record_external_validation") != STATUS_REHEARSED:
        raise ValueError("DualOracleReceiptNotRehearsed")
    if active_receipt.get("record_id") != manifest.get("record_id"):
        raise ValueError("RecordIdMismatch")
    if active_receipt.get("profile") != manifest.get("profile"):
        raise ValueError("ProfileMismatch")
    if active_receipt.get("subjects") != manifest.get("subjects"):
        raise ValueError("SubjectSetMismatch")
    if any(active_receipt.get(name) is not False for name in _RECEIPT_DENIED):
        raise ValueError("ReceiptAuthorityEscalation")
    if custody.get("schema") != CUSTODY_SCHEMA:
        raise ValueError("CustodySchemaUnsupported")
    expected = {
        "custodian_id": KEY_ID,
        "key_id": KEY_ID,
        "namespace": NAMESPACE,
        "record_id": manifest.get("record_id"),
        "source": "HOLODECK_BLACK_BOX_EXPORT_REHEARSAL",
        "transfer_mode": "READ_ONLY",
        "sequence": 1,
        "previous_custody_sha256": None,
        "clock_evidence": "DETERMINISTIC_SIMULATION_CLOCK",
        "subjects": manifest.get("subjects"),
    }
    for name, value in expected.items():
        if custody.get(name) != value:
            raise ValueError(f"Custody{name.title().replace('_', '')}Mismatch")
    custody_id = custody.get("custody_id")
    if not isinstance(custody_id, str) or not custody_id:
        raise ValueError("CustodyIdInvalid")
    if any(custody.get(name) is not False for name in _DENIED):
        raise ValueError("CustodyAuthorityEscalation")
    issued = _timestamp(custody.get("issued_at"), "IssuedAt")
    expires = _timestamp(custody.get("expires_at"), "ExpiresAt")
    now = _timestamp(now_utc, "CurrentTime")
    if expires <= issued or (expires - issued).total_seconds() > MAX_VALIDITY_SECONDS:
        raise ValueError("CustodyValidityWindowInvalid")
    if now < issued:
        raise ValueError("CustodyNotYetValid")
    if now > expires:
        raise ValueError("CustodyExpired")
    return issued, expires


def build_custody_statement(
    manifest: Mapping[str, Any],
    active_receipt: Mapping[str, Any],
    custody: Mapping[str, Any],
    *,
    now_utc: str,
) -> bytes:
    """Build the exact statement signed outside the verifier boundary."""

    _validate_inputs(manifest, active_receipt, custody, now_utc=now_utc)
    statement = {
        "schema": STATEMENT_SCHEMA,
        "namespace": NAMESPACE,
        "key_id": KEY_ID,
        "custody_id": custody["custody_id"],
        "custodian_id": custody["custodian_id"],
        "record_id": manifest["record_id"],
        "profile": manifest["profile"],
        "subjects": manifest["subjects"],
        "manifest_sha256": _sha256(manifest),
        "active_receipt_sha256": _sha256(active_receipt),
        "oracle_receipts": active_receipt["oracle_receipts"],
        "source": custody["source"],
        "transfer_mode": custody["transfer_mode"],
        "sequence": custody["sequence"],
        "previous_custody_sha256": custody["previous_custody_sha256"],
        "clock_evidence": custody["clock_evidence"],
        "issued_at": custody["issued_at"],
        "expires_at": custody["expires_at"],
        **{name: False for name in _DENIED},
    }
    return _canonical(statement)


def evaluate_authenticated_custody(
    manifest: Mapping[str, Any],
    active_receipt: Mapping[str, Any],
    custody: Mapping[str, Any],
    signature: str | None,
    verifier: Callable[[str, bytes, str], bool] | None,
    *,
    now_utc: str,
) -> dict[str, Any]:
    """Verify exact custody evidence without promoting a runtime record."""

    errors: list[str] = []
    statement = b""
    try:
        statement = build_custody_statement(
            manifest, active_receipt, custody, now_utc=now_utc
        )
    except (KeyError, TypeError, ValueError) as error:
        errors.append(str(error) or type(error).__name__)

    verified = False
    if statement and signature is not None and verifier is not None:
        try:
            verified = verifier(KEY_ID, statement, signature) is True
        except (OSError, RuntimeError, TypeError, ValueError):
            verified = False
        if not verified:
            errors.append("CustodianSignatureInvalid")
    elif statement and signature is not None:
        errors.append("CustodianVerifierUnavailable")

    if errors:
        status = STATUS_HOLD
    elif signature is None:
        status = STATUS_SIGNATURE_REQUIRED
    elif verified:
        status = STATUS_AUTHENTICATED
    else:
        status = STATUS_HOLD

    result = {
        "schema": SCHEMA,
        "status": status,
        "record_id": manifest.get("record_id"),
        "custody_id": custody.get("custody_id"),
        "custodian_id": custody.get("custodian_id"),
        "issued_at": custody.get("issued_at"),
        "expires_at": custody.get("expires_at"),
        "key_id": KEY_ID,
        "namespace": NAMESPACE,
        "subjects": manifest.get("subjects", []),
        "manifest_sha256": _sha256(manifest),
        "active_receipt_sha256": _sha256(active_receipt),
        "statement_sha256": hashlib.sha256(statement).hexdigest() if statement else None,
        "custodian_signature_present": signature is not None,
        "custodian_signature_verified": verified,
        "dual_oracle_receipt_verified": not errors or verified,
        "authenticated_custody_rehearsed": status == STATUS_AUTHENTICATED,
        "active_runtime_record_validation": "PENDING",
        "eligible_for_production_trust": False,
        "errors": list(dict.fromkeys(errors)),
        **{name: False for name in _DENIED},
    }
    result["record_sha256"] = _sha256(result)
    return result


__all__ = [
    "CUSTODY_SCHEMA",
    "KEY_ID",
    "NAMESPACE",
    "SCHEMA",
    "STATUS_AUTHENTICATED",
    "STATUS_HOLD",
    "STATUS_SIGNATURE_REQUIRED",
    "build_custody_statement",
    "evaluate_authenticated_custody",
]
