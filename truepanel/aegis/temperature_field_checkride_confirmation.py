"""Offline confirmation of one exact passive temperature field-checkride plan."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from .ssh_verifier import (
    MAX_ALLOWED_SIGNERS_BYTES,
    MAX_SIGNATURE_BYTES,
    validate_allowed_signers_roster,
)
from .temperature_authenticated_acceptance import KEY_ID
from .temperature_calibration_candidate_appraisal import (
    MAX_PUBLIC_BYTES,
    _canonical,
    _snapshot,
)
from .temperature_field_checkride_plan import (
    SCHEMA as PLAN_SCHEMA,
)
from .temperature_field_checkride_plan import (
    STATUS_READY as PLAN_READY,
)
from .temperature_field_checkride_plan import (
    expected_temperature_field_checkride_contract,
)

SCHEMA: Final = "truepanel.aegis-temperature-field-checkride-confirmation/v1"
STATEMENT_SCHEMA: Final = (
    "truepanel.aegis-temperature-field-checkride-confirmation-statement/v1"
)
RECEIPT_SCHEMA: Final = (
    "truepanel.aegis-temperature-field-checkride-confirmation-receipt/v1"
)
NAMESPACE: Final = (
    "truepanel-aegis-temperature-field-checkride-confirmation-v1@truepanel"
)
SCOPE: Final = "operator-supplied-passive-recording-review-only"
STATUS_READY: Final = "READY_FOR_OFFLINE_FIELD_CHECKRIDE_CONFIRMATION_SIGNATURE"
STATUS_ELIGIBLE: Final = "ELIGIBLE_FOR_OPERATOR_SUPPLIED_RECORDING_REVIEW"
STATUS_HELD: Final = "FIELD_CHECKRIDE_CONFIRMATION_HOLD_RECORDED"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_SEPARATE_FIELD_CHECKRIDE_CONFIRMATION"
STATUS_HOLD: Final = "HOLD"
DECISION_CONFIRM: Final = "CONFIRM_OPERATOR_SUPPLIED_PASSIVE_RECORDING_REVIEW"
DECISION_HOLD: Final = "HOLD_FIELD_CHECKRIDE_CONFIRMATION"
MAX_WINDOW: Final = timedelta(hours=2)

_DENIED = (
    "battle_station_access",
    "capture_authority",
    "field_checkride_authority",
    "field_validated",
    "production_validated",
    "candidate_accepted",
    "candidate_installed",
    "runtime_authority",
    "deployment_authority",
    "hardware_authority",
    "storage_write_authority",
    "network_authority",
    "automatic_promotion",
)
_PLAN_KEYS = {
    "schema",
    "status",
    "assembled_at_utc",
    "appraisal_receipt_sha256",
    "dossier_sha256",
    "dossier_subjects",
    "contract",
    "coverage",
    "proof_target",
    "separate_confirmation_required",
    "confirmation_present",
    "recording_present",
    "verification_evidence_present",
    "plan_sha256",
    *_DENIED,
}
_STATEMENT_KEYS = {
    "schema",
    "namespace",
    "scope",
    "key_id",
    "operator_key_fingerprint",
    "prepared_at_utc",
    "expires_at_utc",
    "decision",
    "rationale",
    "plan_sha256",
    "appraisal_receipt_sha256",
    "dossier_sha256",
    "dossier_subjects",
    "contract_sha256",
    "coverage",
    "proof_target",
    "operator_statement",
    "confirmation_present",
    "operator_supplied_recording_review_eligible",
    "recording_present",
    *_DENIED,
}
_RECEIPT_KEYS = {
    "schema",
    "status",
    "recorded_at_utc",
    "decision",
    "rationale",
    "confirmation_statement_sha256",
    "confirmation_signature_sha256",
    "plan_sha256",
    "appraisal_receipt_sha256",
    "dossier_sha256",
    "dossier_subjects",
    "contract_sha256",
    "operator_key_fingerprint",
    "confirmation_present",
    "operator_supplied_recording_review_eligible",
    "recording_present",
    "receipt_sha256",
    *_DENIED,
}
_RATIONALES = {
    "reviewed-passive-plan-exactly-as-written",
    "operator-caution",
    "plan-review-incomplete",
    "external-review-required",
}


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        value if isinstance(value, bytes) else _canonical(value)
    ).hexdigest()


def _window(prepared: str, expires: str, now: str) -> None:
    def parse(value: str) -> datetime:
        if not isinstance(value, str) or not value.endswith("Z"):
            raise ValueError("FieldCheckrideConfirmationTimeInvalid")
        result = datetime.fromisoformat(value[:-1] + "+00:00")
        if result.tzinfo != UTC:
            raise ValueError("FieldCheckrideConfirmationTimeInvalid")
        return result

    prepared_at, expires_at, current = map(parse, (prepared, expires, now))
    if expires_at <= prepared_at or expires_at - prepared_at > MAX_WINDOW:
        raise ValueError("FieldCheckrideConfirmationWindowInvalid")
    if current < prepared_at or current >= expires_at:
        raise ValueError("FieldCheckrideConfirmationExpiredOrNotYetValid")


def _fingerprint(verifier: Any) -> str:
    if getattr(verifier, "namespace", None) != NAMESPACE or getattr(
        verifier, "expected_key_ids", None
    ) != (KEY_ID,):
        raise ValueError("FieldCheckrideConfirmationVerifierPolicyMismatch")
    path = getattr(verifier, "allowed_signers_path", None)
    if not isinstance(path, Path):
        raise ValueError("FieldCheckrideConfirmationVerifierPolicyMismatch")
    return validate_allowed_signers_roster(
        _snapshot(path, MAX_ALLOWED_SIGNERS_BYTES), expected_key_ids=(KEY_ID,)
    )[KEY_ID]


def _plan(path: Path) -> dict[str, Any]:
    payload = _snapshot(path, MAX_PUBLIC_BYTES)
    value = json.loads(payload)
    if (
        not isinstance(value, dict)
        or set(value) != _PLAN_KEYS
        or payload != _canonical(value) + b"\n"
    ):
        raise ValueError("FieldCheckrideConfirmationPlanInvalid")
    unsigned = dict(value)
    claimed = unsigned.pop("plan_sha256")
    if claimed != _sha256(unsigned):
        raise ValueError("FieldCheckrideConfirmationPlanDigestMismatch")
    if (
        value["schema"] != PLAN_SCHEMA
        or value["status"] != PLAN_READY
        or value["contract"] != expected_temperature_field_checkride_contract()
        or value["coverage"] != {"total": 8, "trusted": 8, "gaps": 0}
        or value["proof_target"]
        != {
            "shared_cooling_first_match_sample": 19,
            "isolated_threshold_first_match_sample": 46,
            "lead_samples": 27,
        }
        or value["separate_confirmation_required"] is not True
        or value["confirmation_present"] is not False
        or value["recording_present"] is not False
        or value["verification_evidence_present"] is not False
        or any(value[key] is not False for key in _DENIED)
    ):
        raise ValueError("FieldCheckrideConfirmationPlanPolicyMismatch")
    return value


def build_temperature_field_checkride_confirmation_statement(
    plan_path: str | Path,
    verifier: Any,
    *,
    decision: str,
    rationale: str,
    prepared_at_utc: str,
    expires_at_utc: str,
    now_utc: str,
) -> bytes:
    """Bind one short-lived choice to the exact passive plan."""
    _window(prepared_at_utc, expires_at_utc, now_utc)
    plan = _plan(Path(plan_path))
    if (
        decision not in {DECISION_CONFIRM, DECISION_HOLD}
        or rationale not in _RATIONALES
    ):
        raise ValueError("FieldCheckrideConfirmationChoiceInvalid")
    if (decision == DECISION_CONFIRM) != (
        rationale == "reviewed-passive-plan-exactly-as-written"
    ):
        raise ValueError("FieldCheckrideConfirmationRationaleInvalid")
    eligible = decision == DECISION_CONFIRM
    return _canonical(
        {
            "schema": STATEMENT_SCHEMA,
            "namespace": NAMESPACE,
            "scope": SCOPE,
            "key_id": KEY_ID,
            "operator_key_fingerprint": _fingerprint(verifier),
            "prepared_at_utc": prepared_at_utc,
            "expires_at_utc": expires_at_utc,
            "decision": decision,
            "rationale": rationale,
            "plan_sha256": plan["plan_sha256"],
            "appraisal_receipt_sha256": plan["appraisal_receipt_sha256"],
            "dossier_sha256": plan["dossier_sha256"],
            "dossier_subjects": plan["dossier_subjects"],
            "contract_sha256": _sha256(plan["contract"]),
            "coverage": plan["coverage"],
            "proof_target": plan["proof_target"],
            "operator_statement": "I confirm only review of a separately supplied sanitized recording under this exact passive plan.",
            "confirmation_present": True,
            "operator_supplied_recording_review_eligible": eligible,
            "recording_present": False,
            **{key: False for key in sorted(_DENIED)},
        }
    )


def export_temperature_field_checkride_confirmation_statement(
    plan_path: str | Path, verifier: Any, output_path: str | Path, **kwargs: Any
) -> dict[str, Any]:
    errors: list[str] = []
    statement = b""
    created = False
    try:
        statement = build_temperature_field_checkride_confirmation_statement(
            plan_path, verifier, **kwargs
        )
        destination = Path(output_path)
        if not destination.is_absolute() or destination.exists():
            raise ValueError("FieldCheckrideConfirmationStatementOutputUnavailable")
        descriptor = os.open(
            destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600
        )
        try:
            written = 0
            while written < len(statement):
                written += os.write(descriptor, statement[written:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        created = True
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as error:
        errors.append(str(error) or error.__class__.__name__)
    return {
        "schema": SCHEMA,
        "status": STATUS_READY if created else STATUS_HOLD,
        "statement_created": created,
        "statement_sha256": _sha256(statement) if created else None,
        "private_key_accepted": False,
        "signer_invoked": False,
        "errors": errors,
    }


def _commit(registry: Path, digest: str, receipt: Mapping[str, Any]) -> str:
    if not registry.is_absolute() or registry.is_symlink():
        raise ValueError("FieldCheckrideConfirmationRegistryUnavailable")
    info = registry.stat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("FieldCheckrideConfirmationRegistryUnsafe")
    filename = f"{digest}.json"
    destination = registry / filename
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    try:
        payload = _canonical(receipt) + b"\n"
        written = 0
        while written < len(payload):
            written += os.write(descriptor, payload[written:])
        os.fsync(descriptor)
    except BaseException:
        with suppress(OSError):
            destination.unlink()
        raise
    finally:
        os.close(descriptor)
    return filename


def evaluate_temperature_field_checkride_confirmation(
    plan_path: str | Path,
    verifier: Any,
    statement_path: str | Path,
    signature_path: str | Path,
    registry_path: str | Path,
    *,
    now_utc: str,
) -> dict[str, Any]:
    """Authenticate and immutably record confirmation without execution authority."""
    errors: list[str] = []
    verified = recorded = False
    receipt: dict[str, Any] = {}
    filename: str | None = None
    try:
        plan = _plan(Path(plan_path))
        statement_bytes = _snapshot(Path(statement_path), MAX_PUBLIC_BYTES)
        statement = json.loads(statement_bytes)
        if not isinstance(statement, dict) or set(statement) != _STATEMENT_KEYS:
            raise ValueError("FieldCheckrideConfirmationStatementFieldsInvalid")
        expected = build_temperature_field_checkride_confirmation_statement(
            plan_path,
            verifier,
            decision=statement["decision"],
            rationale=statement["rationale"],
            prepared_at_utc=statement["prepared_at_utc"],
            expires_at_utc=statement["expires_at_utc"],
            now_utc=now_utc,
        )
        if statement_bytes != expected:
            raise ValueError("FieldCheckrideConfirmationStatementMismatch")
        signature = _snapshot(Path(signature_path), MAX_SIGNATURE_BYTES)
        verified = verifier(KEY_ID, statement_bytes, signature.decode("ascii")) is True
        if not verified:
            raise ValueError("FieldCheckrideConfirmationSignatureNotAuthenticated")
        eligible = statement["decision"] == DECISION_CONFIRM
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": STATUS_ELIGIBLE if eligible else STATUS_HELD,
            "recorded_at_utc": now_utc,
            "decision": statement["decision"],
            "rationale": statement["rationale"],
            "confirmation_statement_sha256": _sha256(statement_bytes),
            "confirmation_signature_sha256": _sha256(signature),
            "plan_sha256": plan["plan_sha256"],
            "appraisal_receipt_sha256": plan["appraisal_receipt_sha256"],
            "dossier_sha256": plan["dossier_sha256"],
            "dossier_subjects": plan["dossier_subjects"],
            "contract_sha256": _sha256(plan["contract"]),
            "operator_key_fingerprint": statement["operator_key_fingerprint"],
            "confirmation_present": True,
            "operator_supplied_recording_review_eligible": eligible,
            "recording_present": False,
            **{key: False for key in sorted(_DENIED)},
        }
        receipt["receipt_sha256"] = _sha256(receipt)
        if set(receipt) != _RECEIPT_KEYS:
            raise ValueError("FieldCheckrideConfirmationReceiptFieldsInvalid")
        filename = _commit(Path(registry_path), plan["plan_sha256"], receipt)
        recorded = True
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
    eligible = (
        not errors
        and verified
        and recorded
        and receipt.get("operator_supplied_recording_review_eligible") is True
    )
    held = (
        not errors
        and verified
        and recorded
        and receipt.get("operator_supplied_recording_review_eligible") is False
    )
    return {
        "schema": SCHEMA,
        "status": STATUS_ELIGIBLE if eligible else STATUS_HELD if held else STATUS_HOLD,
        "confirmation_signature_verified": verified,
        "confirmation_recorded": recorded,
        "receipt_filename": filename,
        "receipt_sha256": receipt.get("receipt_sha256") if recorded else None,
        "decision": receipt.get("decision") if recorded else None,
        "confirmation_present": recorded,
        "operator_supplied_recording_review_eligible": eligible,
        "recording_present": False,
        **{key: False for key in _DENIED},
        "errors": errors,
    }


def verify_recorded_temperature_field_checkride_confirmation(
    plan_path: str | Path,
    verifier: Any,
    statement_path: str | Path,
    signature_path: str | Path,
    receipt_path: str | Path,
    *,
    now_utc: str,
) -> dict[str, Any]:
    """Reverify one immutable confirmation without writing or adding authority."""
    plan = _plan(Path(plan_path))
    statement_bytes = _snapshot(Path(statement_path), MAX_PUBLIC_BYTES)
    statement = json.loads(statement_bytes)
    if not isinstance(statement, dict) or set(statement) != _STATEMENT_KEYS:
        raise ValueError("FieldCheckrideConfirmationStatementFieldsInvalid")
    expected_statement = build_temperature_field_checkride_confirmation_statement(
        plan_path,
        verifier,
        decision=statement["decision"],
        rationale=statement["rationale"],
        prepared_at_utc=statement["prepared_at_utc"],
        expires_at_utc=statement["expires_at_utc"],
        now_utc=now_utc,
    )
    if statement_bytes != expected_statement:
        raise ValueError("FieldCheckrideConfirmationStatementMismatch")
    signature = _snapshot(Path(signature_path), MAX_SIGNATURE_BYTES)
    if verifier(KEY_ID, statement_bytes, signature.decode("ascii")) is not True:
        raise ValueError("FieldCheckrideConfirmationSignatureNotAuthenticated")
    receipt_bytes = _snapshot(Path(receipt_path), MAX_PUBLIC_BYTES)
    receipt = json.loads(receipt_bytes)
    if (
        not isinstance(receipt, dict)
        or set(receipt) != _RECEIPT_KEYS
        or receipt_bytes != _canonical(receipt) + b"\n"
    ):
        raise ValueError("FieldCheckrideConfirmationReceiptInvalid")
    unsigned = dict(receipt)
    claimed = unsigned.pop("receipt_sha256")
    if claimed != _sha256(unsigned):
        raise ValueError("FieldCheckrideConfirmationReceiptDigestMismatch")
    eligible = statement["decision"] == DECISION_CONFIRM
    expected_receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": STATUS_ELIGIBLE if eligible else STATUS_HELD,
        "recorded_at_utc": receipt["recorded_at_utc"],
        "decision": statement["decision"],
        "rationale": statement["rationale"],
        "confirmation_statement_sha256": _sha256(statement_bytes),
        "confirmation_signature_sha256": _sha256(signature),
        "plan_sha256": plan["plan_sha256"],
        "appraisal_receipt_sha256": plan["appraisal_receipt_sha256"],
        "dossier_sha256": plan["dossier_sha256"],
        "dossier_subjects": plan["dossier_subjects"],
        "contract_sha256": _sha256(plan["contract"]),
        "operator_key_fingerprint": statement["operator_key_fingerprint"],
        "confirmation_present": True,
        "operator_supplied_recording_review_eligible": eligible,
        "recording_present": False,
        **{key: False for key in sorted(_DENIED)},
    }
    expected_receipt["receipt_sha256"] = _sha256(expected_receipt)
    if receipt != expected_receipt:
        raise ValueError("FieldCheckrideConfirmationReceiptMismatch")
    return receipt


def pending_temperature_field_checkride_confirmation(
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    ready = plan.get("plan_ready") is True
    return {
        "schema": SCHEMA,
        "status": STATUS_REQUIRED if ready else STATUS_HOLD,
        "plan_present": ready,
        "confirmation_present": False,
        "operator_supplied_recording_review_eligible": False,
        "recording_present": False,
        **{key: False for key in _DENIED},
        "next_action": "Export and sign one exact CONFIRM or HOLD statement offline; confirmation permits review only after an operator separately supplies a sanitized recording.",
    }


__all__ = [
    "DECISION_CONFIRM",
    "DECISION_HOLD",
    "NAMESPACE",
    "SCHEMA",
    "STATUS_ELIGIBLE",
    "STATUS_HELD",
    "STATUS_HOLD",
    "STATUS_READY",
    "build_temperature_field_checkride_confirmation_statement",
    "evaluate_temperature_field_checkride_confirmation",
    "export_temperature_field_checkride_confirmation_statement",
    "pending_temperature_field_checkride_confirmation",
    "verify_recorded_temperature_field_checkride_confirmation",
]
