"""SSHSIG-authenticated development acceptance for the temperature candidate."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from typing import Any, Final

from .temperature_development_acceptance import (
    STATUS_ACTION_REQUIRED,
    STATUS_DEVELOPMENT_ACCEPTED,
    evaluate_temperature_development_acceptance,
)

SCHEMA: Final = "truepanel.aegis-temperature-authenticated-acceptance/v1"
STATEMENT_SCHEMA: Final = "truepanel.aegis-temperature-acceptance-statement/v1"
NAMESPACE: Final = "truepanel-aegis-temperature-development-v1@truepanel"
KEY_ID: Final = "jt-development-review"
STATUS_SIGNATURE_REQUIRED: Final = "ACTION_REQUIRED_OPERATOR_SIGNATURE"
STATUS_AUTHENTICATED: Final = "AUTHENTICATED_DEVELOPMENT_ACCEPTED_FOR_REVIEW"
STATUS_HOLD: Final = "HOLD"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def build_temperature_acceptance_statement(
    candidate: Mapping[str, Any],
    appraisal: Mapping[str, Any],
    confirmation: Mapping[str, Any],
    *,
    now_utc: str,
) -> bytes:
    """Return the one canonical statement JT signs outside TruePanel."""

    base = evaluate_temperature_development_acceptance(
        candidate, appraisal, confirmation, now_utc=now_utc
    )
    if base["status"] != STATUS_DEVELOPMENT_ACCEPTED:
        raise ValueError("DevelopmentConfirmationNotAcceptable")
    statement = {
        "schema": STATEMENT_SCHEMA,
        "namespace": NAMESPACE,
        "key_id": KEY_ID,
        "scope": base["scope"],
        "confirmation_record_sha256": base["record_sha256"],
        "confirmation_sha256": _sha256(confirmation),
        "subjects": base["subjects"],
        "accepted": False,
        "installed": False,
        "runtime_authority": False,
        "production_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "network_authority": False,
        "automatic_promotion": False,
    }
    return _canonical(statement)


def evaluate_authenticated_temperature_acceptance(
    candidate: Mapping[str, Any],
    appraisal: Mapping[str, Any],
    confirmation: Mapping[str, Any] | None,
    signature: str | None,
    verifier: Callable[[str, bytes, str], bool] | None,
    *,
    now_utc: str,
) -> dict[str, Any]:
    """Verify JT's detached signature without gaining operational authority."""

    base = evaluate_temperature_development_acceptance(
        candidate, appraisal, confirmation, now_utc=now_utc
    )
    errors = list(base["errors"])
    statement = b""
    signature_verified = False

    if base["status"] == STATUS_DEVELOPMENT_ACCEPTED:
        try:
            statement = build_temperature_acceptance_statement(
                candidate, appraisal, confirmation or {}, now_utc=now_utc
            )
        except (TypeError, ValueError):
            errors.append("authenticated statement could not be reconstructed")
        if statement and signature is not None and verifier is not None:
            try:
                signature_verified = verifier(KEY_ID, statement, signature) is True
            except (OSError, RuntimeError, TypeError, ValueError):
                signature_verified = False
            if not signature_verified:
                errors.append("operator SSHSIG verification failed")
        elif statement and signature is not None:
            errors.append("operator SSHSIG verifier unavailable")

    if base["status"] == STATUS_ACTION_REQUIRED:
        status = STATUS_ACTION_REQUIRED
    elif base["status"] == STATUS_HOLD or errors:
        status = STATUS_HOLD
    elif signature is None:
        status = STATUS_SIGNATURE_REQUIRED
    elif signature_verified:
        status = STATUS_AUTHENTICATED
    else:
        status = STATUS_HOLD

    result = {
        "schema": SCHEMA,
        "status": status,
        "operator_id": base["operator_id"],
        "key_id": KEY_ID,
        "namespace": NAMESPACE,
        "scope": base["scope"],
        "subjects": base["subjects"],
        "confirmation_present": base["confirmation_present"],
        "operator_signature_present": signature is not None,
        "operator_signature_verified": signature_verified,
        "development_review_accepted": status == STATUS_AUTHENTICATED,
        "statement_sha256": hashlib.sha256(statement).hexdigest()
        if statement
        else None,
        "errors": list(dict.fromkeys(errors)),
        "accepted": False,
        "installed": False,
        "runtime_authority": False,
        "production_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "network_authority": False,
        "automatic_promotion": False,
    }
    result["record_sha256"] = _sha256(result)
    return result


__all__ = [
    "KEY_ID",
    "NAMESPACE",
    "SCHEMA",
    "STATEMENT_SCHEMA",
    "STATUS_AUTHENTICATED",
    "STATUS_HOLD",
    "STATUS_SIGNATURE_REQUIRED",
    "build_temperature_acceptance_statement",
    "evaluate_authenticated_temperature_acceptance",
]
