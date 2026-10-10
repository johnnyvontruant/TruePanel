"""Development-only operator acceptance for the appraised temperature candidate."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

REQUEST_SCHEMA = "truepanel.aegis-temperature-development-acceptance-request/v1"
CONFIRMATION_SCHEMA = "truepanel.aegis-temperature-development-confirmation/v1"
RECORD_SCHEMA = "truepanel.aegis-temperature-development-acceptance/v1"
STATUS_ACTION_REQUIRED = "ACTION_REQUIRED_OPERATOR_CONFIRMATION"
STATUS_DEVELOPMENT_ACCEPTED = "DEVELOPMENT_ACCEPTED_FOR_REVIEW"
STATUS_HOLD = "HOLD"
OPERATOR_ID = "jt"
SCOPE = "development-candidate-review-only"
REQUIRED_STATEMENT = (
    "I accept this exact temperature coverage candidate for development review only."
)
PINNED_APPRAISAL = {
    "candidate_document_sha256": "495fba0a70f2ea07e07634cd8fc7678bc463b66af8ef461299c8ce5271376029",
    "appraisal_sha256": "8a690de3a16d02cde848e3aea2a11dd7b4fa7d1fd7a4eb257fdbfe9df07021c1",
    "appraisal_document_sha256": "1febfaf57069edd58fb75eddcb5d6cab6b514f016d701f3b073c35c658812ea5",
}


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    return parsed if parsed.tzinfo == UTC else None


def prepare_temperature_development_acceptance(
    candidate: Mapping[str, Any], appraisal: Mapping[str, Any]
) -> dict[str, Any]:
    """Build the exact public request that JT may explicitly acknowledge."""

    return {
        "schema": REQUEST_SCHEMA,
        "status": STATUS_ACTION_REQUIRED,
        "operator_id": OPERATOR_ID,
        "scope": SCOPE,
        "required_statement": REQUIRED_STATEMENT,
        "subjects": {
            "candidate_document_sha256": _sha256(candidate),
            "appraisal_sha256": str(appraisal.get("appraisal_sha256", "")),
            "appraisal_document_sha256": _sha256(appraisal),
        },
        "authentication": "operator-provided-confirmation-not-present",
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


def evaluate_temperature_development_acceptance(
    candidate: Mapping[str, Any],
    appraisal: Mapping[str, Any],
    confirmation: Mapping[str, Any] | None,
    *,
    now_utc: str,
) -> dict[str, Any]:
    """Fail closed unless JT confirms the exact appraised development subject.

    This is an explicit human-attestation record, not cryptographic identity
    proof.  It can advance development review only and is structurally unable
    to accept or install the runtime matrix.
    """

    proposed = deepcopy(dict(candidate))
    reviewed = deepcopy(dict(appraisal))
    request = prepare_temperature_development_acceptance(proposed, reviewed)
    errors: list[str] = []
    subjects = request["subjects"]

    if subjects != PINNED_APPRAISAL:
        errors.append("candidate or appraisal does not match the reviewed subject")
    if reviewed.get("status") != "READY_FOR_INDEPENDENT_REVIEW":
        errors.append("appraisal is not ready for independent review")
    if reviewed.get("ready_for_independent_review") is not True:
        errors.append("appraisal readiness is not asserted")
    if reviewed.get("accepted") is not False or reviewed.get("installed") is not False:
        errors.append("appraisal authority boundary is invalid")

    now = _utc(now_utc)
    if now is None:
        errors.append("trusted UTC is invalid")

    acknowledged = confirmation is not None
    if confirmation is not None:
        supplied = dict(confirmation)
        allowed = {
            "schema",
            "operator_id",
            "scope",
            "statement",
            "subjects",
            "issued_at",
            "expires_at",
        }
        if set(supplied) != allowed:
            errors.append("confirmation has unknown or missing fields")
        if supplied.get("schema") != CONFIRMATION_SCHEMA:
            errors.append("confirmation schema is invalid")
        if supplied.get("operator_id") != OPERATOR_ID:
            errors.append("confirmation operator is not JT")
        if supplied.get("scope") != SCOPE:
            errors.append("confirmation scope is not development-only")
        if supplied.get("statement") != REQUIRED_STATEMENT:
            errors.append("operator statement is not exact")
        if supplied.get("subjects") != subjects:
            errors.append("confirmation subjects do not match the request")
        issued = _utc(supplied.get("issued_at"))
        expires = _utc(supplied.get("expires_at"))
        if issued is None or expires is None:
            errors.append("confirmation validity window is invalid")
        elif not issued < expires or (expires - issued).total_seconds() > 86400:
            errors.append("confirmation validity window exceeds policy")
        elif now is not None and not issued <= now <= expires:
            errors.append("confirmation is not current")

    if not acknowledged and not errors:
        status = STATUS_ACTION_REQUIRED
    elif errors:
        status = STATUS_HOLD
    else:
        status = STATUS_DEVELOPMENT_ACCEPTED

    result = {
        "schema": RECORD_SCHEMA,
        "status": status,
        "development_review_accepted": status == STATUS_DEVELOPMENT_ACCEPTED,
        "operator_id": OPERATOR_ID,
        "scope": SCOPE,
        "subjects": subjects,
        "confirmation_present": acknowledged,
        "confirmation_authenticated": False,
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
    "CONFIRMATION_SCHEMA",
    "OPERATOR_ID",
    "PINNED_APPRAISAL",
    "REQUIRED_STATEMENT",
    "REQUEST_SCHEMA",
    "RECORD_SCHEMA",
    "SCOPE",
    "STATUS_ACTION_REQUIRED",
    "STATUS_DEVELOPMENT_ACCEPTED",
    "STATUS_HOLD",
    "evaluate_temperature_development_acceptance",
    "prepare_temperature_development_acceptance",
]
