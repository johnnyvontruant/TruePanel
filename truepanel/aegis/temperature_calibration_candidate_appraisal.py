"""Operator-authenticated appraisal of one exact calibration candidate dossier."""

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
from .temperature_calibration_candidate_dossier import (
    SCHEMA as DOSSIER_SCHEMA,
)
from .temperature_calibration_candidate_dossier import (
    STATUS_READY as DOSSIER_READY,
)

SCHEMA: Final = "truepanel.aegis-temperature-calibration-candidate-appraisal/v1"
STATEMENT_SCHEMA: Final = (
    "truepanel.aegis-temperature-calibration-candidate-appraisal-statement/v1"
)
RECEIPT_SCHEMA: Final = (
    "truepanel.aegis-temperature-calibration-candidate-appraisal-receipt/v1"
)
NAMESPACE: Final = (
    "truepanel-aegis-temperature-calibration-candidate-appraisal-v1@truepanel"
)
SCOPE: Final = "manual-field-checkride-planning-only"
STATUS_READY: Final = "READY_FOR_OFFLINE_CALIBRATION_CANDIDATE_APPRAISAL_SIGNATURE"
STATUS_APPROVED: Final = "APPROVED_FOR_MANUAL_FIELD_CHECKRIDE_PLANNING"
STATUS_HELD: Final = "CALIBRATION_CANDIDATE_APPRAISAL_HOLD_RECORDED"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_AUTHENTICATED_CANDIDATE_APPRAISAL"
STATUS_HOLD: Final = "HOLD"
DECISION_APPROVE: Final = "APPROVE_FOR_MANUAL_FIELD_CHECKRIDE_PLANNING"
DECISION_HOLD: Final = "HOLD_CALIBRATION_CANDIDATE_APPRAISAL"
MAX_WINDOW: Final = timedelta(hours=2)
MAX_PUBLIC_BYTES: Final = 2 * 1024 * 1024

_AUTHORITY_KEYS = {
    "field_validated",
    "production_validated",
    "candidate_accepted",
    "candidate_installed",
    "field_checkride_authority",
    "runtime_authority",
    "deployment_authority",
    "hardware_authority",
    "storage_write_authority",
    "network_authority",
    "automatic_promotion",
}
_DOSSIER_KEYS = {
    "schema",
    "status",
    "assembled_at_utc",
    "decision",
    "subjects",
    "coverage",
    "proof",
    "limitations",
    "dossier_sha256",
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
    "dossier_sha256",
    "dossier_subjects",
    "coverage",
    "proof",
    "operator_statement",
    "manual_field_checkride_planning_eligible",
    *_AUTHORITY_KEYS,
}
_RECEIPT_KEYS = {
    "schema",
    "status",
    "recorded_at_utc",
    "decision",
    "rationale",
    "appraisal_statement_sha256",
    "appraisal_signature_sha256",
    "dossier_sha256",
    "dossier_subjects",
    "operator_key_fingerprint",
    "manual_field_checkride_planning_eligible",
    "receipt_sha256",
    *_AUTHORITY_KEYS,
}
_RATIONALES = {
    "evidence-complete-for-manual-field-checkride-planning",
    "operator-caution",
    "dossier-evidence-insufficient",
    "external-review-required",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical(value)
    return hashlib.sha256(payload).hexdigest()


def _utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("CalibrationCandidateAppraisalTimeInvalid")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC:
        raise ValueError("CalibrationCandidateAppraisalTimeInvalid")
    return parsed


def _window(prepared_at_utc: str, expires_at_utc: str, now_utc: str) -> None:
    prepared, expires, now = map(_utc, (prepared_at_utc, expires_at_utc, now_utc))
    if expires <= prepared or expires - prepared > MAX_WINDOW:
        raise ValueError("CalibrationCandidateAppraisalWindowInvalid")
    if now < prepared or now >= expires:
        raise ValueError("CalibrationCandidateAppraisalExpiredOrNotYetValid")


def _snapshot(path: Path, maximum: int) -> bytes:
    if not path.is_absolute() or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("ProtectedCalibrationCandidateAppraisalFileUnavailable")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_mode & 0o022
            or before.st_size <= 0
            or before.st_size > maximum
        ):
            raise ValueError("ProtectedCalibrationCandidateAppraisalFileInvalid")
        payload = b""
        while len(payload) <= maximum:
            chunk = os.read(descriptor, min(65_536, maximum + 1 - len(payload)))
            if not chunk:
                break
            payload += chunk
        after = os.fstat(descriptor)

        def identity(item: os.stat_result) -> tuple[int, ...]:
            return (
                item.st_dev,
                item.st_ino,
                item.st_mode,
                item.st_uid,
                item.st_size,
                item.st_mtime_ns,
                item.st_ctime_ns,
            )

        if identity(before) != identity(after) or len(payload) > maximum:
            raise ValueError("ProtectedCalibrationCandidateAppraisalFileChanged")
        return payload
    finally:
        os.close(descriptor)


def _fingerprint(verifier: Any) -> str:
    if getattr(verifier, "namespace", None) != NAMESPACE or getattr(
        verifier, "expected_key_ids", None
    ) != (KEY_ID,):
        raise ValueError("CalibrationCandidateAppraisalVerifierPolicyMismatch")
    path = getattr(verifier, "allowed_signers_path", None)
    if not isinstance(path, Path):
        raise ValueError("CalibrationCandidateAppraisalVerifierPolicyMismatch")
    return validate_allowed_signers_roster(
        _snapshot(path, MAX_ALLOWED_SIGNERS_BYTES), expected_key_ids=(KEY_ID,)
    )[KEY_ID]


def _dossier(path: Path) -> dict[str, Any]:
    payload = _snapshot(path, MAX_PUBLIC_BYTES)
    value = json.loads(payload)
    if (
        not isinstance(value, dict)
        or set(value) != _DOSSIER_KEYS
        or payload != _canonical(value) + b"\n"
    ):
        raise ValueError("CalibrationCandidateAppraisalDossierInvalid")
    unsigned = dict(value)
    claimed = unsigned.pop("dossier_sha256")
    if claimed != _sha256(unsigned):
        raise ValueError("CalibrationCandidateAppraisalDossierDigestMismatch")
    if (
        value["schema"] != DOSSIER_SCHEMA
        or value["status"] != DOSSIER_READY
        or value["coverage"] != {"total": 8, "trusted": 8, "gaps": 0}
        or value["proof"]
        != {
            "lead_samples": 27,
            "passing_accepts": 1,
            "failing_accepts": 0,
        }
        or any(value[key] is not False for key in _AUTHORITY_KEYS if key in value)
    ):
        raise ValueError("CalibrationCandidateAppraisalDossierPolicyMismatch")
    required_subjects = {
        "decision_receipt_sha256",
        "review_receipt_sha256",
        "score_receipt_sha256",
        "score_sha256",
        "detector_contract_sha256",
        "recovery_coverage_matrix_sha256",
        "holodeck_evidence_sha256",
    }
    if set(value["subjects"]) != required_subjects or any(
        not isinstance(digest, str) or len(digest) != 64
        for digest in value["subjects"].values()
    ):
        raise ValueError("CalibrationCandidateAppraisalDossierSubjectsInvalid")
    return value


def _validate_choice(decision: str, rationale: str) -> None:
    if (
        decision not in {DECISION_APPROVE, DECISION_HOLD}
        or rationale not in _RATIONALES
    ):
        raise ValueError("CalibrationCandidateAppraisalChoiceInvalid")
    if decision == DECISION_APPROVE and rationale != (
        "evidence-complete-for-manual-field-checkride-planning"
    ):
        raise ValueError("CalibrationCandidateAppraisalApprovalRationaleInvalid")
    if decision == DECISION_HOLD and rationale == (
        "evidence-complete-for-manual-field-checkride-planning"
    ):
        raise ValueError("CalibrationCandidateAppraisalHoldRationaleInvalid")


def build_temperature_calibration_candidate_appraisal_statement(
    dossier_path: str | Path,
    verifier: Any,
    *,
    decision: str,
    rationale: str,
    prepared_at_utc: str,
    expires_at_utc: str,
    now_utc: str,
) -> bytes:
    """Bind one explicit operator appraisal to the exact dossier."""
    _window(prepared_at_utc, expires_at_utc, now_utc)
    dossier = _dossier(Path(dossier_path))
    fingerprint = _fingerprint(verifier)
    _validate_choice(decision, rationale)
    eligible = decision == DECISION_APPROVE
    statement = {
        "schema": STATEMENT_SCHEMA,
        "namespace": NAMESPACE,
        "scope": SCOPE,
        "key_id": KEY_ID,
        "operator_key_fingerprint": fingerprint,
        "prepared_at_utc": prepared_at_utc,
        "expires_at_utc": expires_at_utc,
        "decision": decision,
        "rationale": rationale,
        "dossier_sha256": dossier["dossier_sha256"],
        "dossier_subjects": dossier["subjects"],
        "coverage": dossier["coverage"],
        "proof": dossier["proof"],
        "operator_statement": "I appraise this exact development-only dossier for manual field-checkride planning.",
        "manual_field_checkride_planning_eligible": eligible,
        **{key: False for key in sorted(_AUTHORITY_KEYS)},
    }
    return _canonical(statement)


def export_temperature_calibration_candidate_appraisal_statement(
    dossier_path: str | Path,
    verifier: Any,
    output_path: str | Path,
    **kwargs: Any,
) -> dict[str, Any]:
    errors: list[str] = []
    created = False
    statement = b""
    try:
        statement = build_temperature_calibration_candidate_appraisal_statement(
            dossier_path, verifier, **kwargs
        )
        destination = Path(output_path)
        if not destination.is_absolute() or destination.exists():
            raise ValueError("CalibrationCandidateAppraisalStatementOutputUnavailable")
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


def _commit_receipt(
    registry: Path, dossier_digest: str, receipt: Mapping[str, Any]
) -> str:
    if not registry.is_absolute() or registry.is_symlink():
        raise ValueError("CalibrationCandidateAppraisalRegistryUnavailable")
    info = registry.stat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("CalibrationCandidateAppraisalRegistryUnsafe")
    filename = f"{dossier_digest}.json"
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


def evaluate_temperature_calibration_candidate_appraisal(
    dossier_path: str | Path,
    verifier: Any,
    statement_path: str | Path,
    signature_path: str | Path,
    appraisal_registry: str | Path,
    *,
    now_utc: str,
) -> dict[str, Any]:
    """Verify and immutably record an appraisal without operational authority."""
    errors: list[str] = []
    verified = False
    recorded = False
    receipt: dict[str, Any] = {}
    filename: str | None = None
    try:
        dossier = _dossier(Path(dossier_path))
        statement_bytes = _snapshot(Path(statement_path), MAX_PUBLIC_BYTES)
        statement = json.loads(statement_bytes)
        if not isinstance(statement, dict) or set(statement) != _STATEMENT_KEYS:
            raise ValueError("CalibrationCandidateAppraisalStatementFieldsInvalid")
        expected = build_temperature_calibration_candidate_appraisal_statement(
            dossier_path,
            verifier,
            decision=statement["decision"],
            rationale=statement["rationale"],
            prepared_at_utc=statement["prepared_at_utc"],
            expires_at_utc=statement["expires_at_utc"],
            now_utc=now_utc,
        )
        if statement_bytes != expected:
            raise ValueError("CalibrationCandidateAppraisalStatementMismatch")
        signature = _snapshot(Path(signature_path), MAX_SIGNATURE_BYTES)
        verified = verifier(KEY_ID, statement_bytes, signature.decode("ascii")) is True
        if not verified:
            raise ValueError("CalibrationCandidateAppraisalSignatureNotAuthenticated")
        eligible = statement["decision"] == DECISION_APPROVE
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": STATUS_APPROVED if eligible else STATUS_HELD,
            "recorded_at_utc": now_utc,
            "decision": statement["decision"],
            "rationale": statement["rationale"],
            "appraisal_statement_sha256": _sha256(statement_bytes),
            "appraisal_signature_sha256": _sha256(signature),
            "dossier_sha256": dossier["dossier_sha256"],
            "dossier_subjects": dossier["subjects"],
            "operator_key_fingerprint": statement["operator_key_fingerprint"],
            "manual_field_checkride_planning_eligible": eligible,
            **{key: False for key in sorted(_AUTHORITY_KEYS)},
        }
        receipt["receipt_sha256"] = _sha256(receipt)
        if set(receipt) != _RECEIPT_KEYS:
            raise ValueError("CalibrationCandidateAppraisalReceiptFieldsInvalid")
        filename = _commit_receipt(
            Path(appraisal_registry), dossier["dossier_sha256"], receipt
        )
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
    approved = (
        not errors
        and verified
        and recorded
        and receipt.get("manual_field_checkride_planning_eligible") is True
    )
    held = (
        not errors
        and verified
        and recorded
        and receipt.get("manual_field_checkride_planning_eligible") is False
    )
    return {
        "schema": SCHEMA,
        "status": STATUS_APPROVED if approved else STATUS_HELD if held else STATUS_HOLD,
        "appraisal_signature_verified": verified,
        "appraisal_recorded": recorded,
        "receipt_filename": filename,
        "receipt_sha256": receipt.get("receipt_sha256") if recorded else None,
        "decision": receipt.get("decision") if recorded else None,
        "manual_field_checkride_planning_eligible": approved,
        "candidate_accepted": False,
        "candidate_installed": False,
        "field_checkride_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "automatic_promotion": False,
        "errors": errors,
    }


def verify_recorded_temperature_calibration_candidate_appraisal(
    dossier_path: str | Path,
    verifier: Any,
    statement_path: str | Path,
    signature_path: str | Path,
    receipt_path: str | Path,
    *,
    now_utc: str,
) -> dict[str, Any]:
    """Reverify one immutable appraisal without writing or expanding authority."""
    dossier = _dossier(Path(dossier_path))
    statement_bytes = _snapshot(Path(statement_path), MAX_PUBLIC_BYTES)
    statement = json.loads(statement_bytes)
    if not isinstance(statement, dict) or set(statement) != _STATEMENT_KEYS:
        raise ValueError("CalibrationCandidateAppraisalStatementFieldsInvalid")
    expected_statement = build_temperature_calibration_candidate_appraisal_statement(
        dossier_path,
        verifier,
        decision=statement["decision"],
        rationale=statement["rationale"],
        prepared_at_utc=statement["prepared_at_utc"],
        expires_at_utc=statement["expires_at_utc"],
        now_utc=now_utc,
    )
    if statement_bytes != expected_statement:
        raise ValueError("CalibrationCandidateAppraisalStatementMismatch")
    signature = _snapshot(Path(signature_path), MAX_SIGNATURE_BYTES)
    if verifier(KEY_ID, statement_bytes, signature.decode("ascii")) is not True:
        raise ValueError("CalibrationCandidateAppraisalSignatureNotAuthenticated")
    receipt_bytes = _snapshot(Path(receipt_path), MAX_PUBLIC_BYTES)
    receipt = json.loads(receipt_bytes)
    if (
        not isinstance(receipt, dict)
        or set(receipt) != _RECEIPT_KEYS
        or receipt_bytes != _canonical(receipt) + b"\n"
    ):
        raise ValueError("CalibrationCandidateAppraisalReceiptInvalid")
    unsigned = dict(receipt)
    claimed = unsigned.pop("receipt_sha256")
    if claimed != _sha256(unsigned):
        raise ValueError("CalibrationCandidateAppraisalReceiptDigestMismatch")
    eligible = statement["decision"] == DECISION_APPROVE
    expected_receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": STATUS_APPROVED if eligible else STATUS_HELD,
        "recorded_at_utc": receipt["recorded_at_utc"],
        "decision": statement["decision"],
        "rationale": statement["rationale"],
        "appraisal_statement_sha256": _sha256(statement_bytes),
        "appraisal_signature_sha256": _sha256(signature),
        "dossier_sha256": dossier["dossier_sha256"],
        "dossier_subjects": dossier["subjects"],
        "operator_key_fingerprint": statement["operator_key_fingerprint"],
        "manual_field_checkride_planning_eligible": eligible,
        **{key: False for key in sorted(_AUTHORITY_KEYS)},
    }
    expected_receipt["receipt_sha256"] = _sha256(expected_receipt)
    if receipt != expected_receipt:
        raise ValueError("CalibrationCandidateAppraisalReceiptMismatch")
    return receipt


def pending_temperature_calibration_candidate_appraisal(
    dossier: Mapping[str, Any],
) -> dict[str, Any]:
    ready = dossier.get("candidate_review_ready") is True
    return {
        "schema": SCHEMA,
        "status": STATUS_REQUIRED if ready else STATUS_HOLD,
        "candidate_dossier_present": ready,
        "operator_appraisal_present": False,
        "manual_field_checkride_planning_eligible": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "field_checkride_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "automatic_promotion": False,
        "next_action": "Inspect the exact dossier and record one offline-signed APPROVE or HOLD appraisal.",
    }


__all__ = [
    "DECISION_APPROVE",
    "DECISION_HOLD",
    "NAMESPACE",
    "SCHEMA",
    "STATUS_APPROVED",
    "STATUS_HELD",
    "STATUS_HOLD",
    "STATUS_READY",
    "build_temperature_calibration_candidate_appraisal_statement",
    "evaluate_temperature_calibration_candidate_appraisal",
    "export_temperature_calibration_candidate_appraisal_statement",
    "pending_temperature_calibration_candidate_appraisal",
    "verify_recorded_temperature_calibration_candidate_appraisal",
]
