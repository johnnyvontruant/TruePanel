"""Signed binding between pre-label detector evidence and calibration admission."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from .ssh_verifier import MAX_SIGNATURE_BYTES
from .temperature_authenticated_acceptance import KEY_ID
from .temperature_calibration_admission import (
    MAX_PUBLIC_BYTES,
    _fingerprint,
    _snapshot,
)
from .temperature_calibration_admission import (
    NAMESPACE as ADMISSION_NAMESPACE,
)
from .temperature_detector_result import SCHEMA as RESULT_SCHEMA
from .temperature_detector_result import (
    build_temperature_detector_result,
)

SCHEMA: Final = "truepanel.aegis-temperature-detector-result-binding/v1"
STATEMENT_SCHEMA: Final = (
    "truepanel.aegis-temperature-detector-result-binding-statement/v1"
)
NAMESPACE: Final = "truepanel-aegis-temperature-detector-result-binding-v1@truepanel"
SCOPE: Final = "calibration-analysis-only"
STATUS_READY: Final = "READY_FOR_OFFLINE_DETECTOR_RESULT_BINDING_SIGNATURE"
STATUS_BOUND: Final = "DETECTOR_RESULT_BOUND_FOR_CALIBRATION_REVIEW"
STATUS_HOLD: Final = "HOLD"
MAX_WINDOW: Final = timedelta(hours=2)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("DetectorBindingTimeInvalid")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC:
        raise ValueError("DetectorBindingTimeInvalid")
    return parsed


def _negative_authority(record: Mapping[str, Any]) -> None:
    fields = (
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
    if any(record.get(name) is not False for name in fields):
        raise ValueError("DetectorBindingAuthorityEscalation")


def _materials(
    recording_path: str | Path,
    detector_result_path: str | Path,
    admission_statement_path: str | Path,
    admission_signature_path: str | Path,
    admission_verifier: Any,
    binding_verifier: Any,
) -> tuple[dict[str, Any], bytes, bytes, dict[str, Any], str]:
    admission_path, admission_fingerprint = _fingerprint(
        admission_verifier, ADMISSION_NAMESPACE
    )
    binding_path, binding_fingerprint = _fingerprint(binding_verifier, NAMESPACE)
    if admission_path != binding_path or admission_fingerprint != binding_fingerprint:
        raise ValueError("DetectorBindingTrustRootMismatch")
    admission = _snapshot(Path(admission_statement_path), MAX_PUBLIC_BYTES)
    admission_signature = _snapshot(
        Path(admission_signature_path), MAX_SIGNATURE_BYTES
    )
    try:
        admission_signature_text = admission_signature.decode("ascii")
        admission_data = json.loads(admission)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("DetectorBindingAdmissionInvalid") from error
    if admission_verifier(KEY_ID, admission, admission_signature_text) is not True:
        raise ValueError("DetectorBindingAdmissionSignatureNotAuthenticated")
    if (
        admission_data.get("schema")
        != "truepanel.aegis-temperature-calibration-admission-statement/v1"
        or admission_data.get("namespace") != ADMISSION_NAMESPACE
        or admission_data.get("scope")
        != "temperature-calibration-corpus-import-only"
        or admission_data.get("key_id") != KEY_ID
        or admission_data.get("eligible_for_corpus_import") is not True
        or not isinstance(admission_data.get("labels"), dict)
    ):
        raise ValueError("DetectorBindingAdmissionInvalid")
    if set(admission_data) != {
        "schema",
        "namespace",
        "scope",
        "key_id",
        "operator_key_fingerprint",
        "prepared_at_utc",
        "expires_at_utc",
        "field_review_receipt_sha256",
        "field_review_statement_sha256",
        "recording_sha256",
        "recording_bytes",
        "frame_count",
        "labels",
        "label_statement",
        "eligible_for_corpus_import",
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
    }:
        raise ValueError("DetectorBindingAdmissionShapeInvalid")
    _negative_authority(admission_data)

    detector_payload = _snapshot(Path(detector_result_path), MAX_PUBLIC_BYTES)
    try:
        detector_data = json.loads(detector_payload)
    except json.JSONDecodeError as error:
        raise ValueError("DetectorBindingResultInvalid") from error
    if detector_data.get("schema") != RESULT_SCHEMA:
        raise ValueError("DetectorBindingResultInvalid")
    expected = build_temperature_detector_result(
        recording_path, generated_at_utc=detector_data.get("generated_at_utc")
    )
    if detector_data != expected:
        raise ValueError("DetectorBindingResultMismatch")
    if (
        detector_data.get("label_blind") is not True
        or detector_data.get("labels_present") is not False
    ):
        raise ValueError("DetectorBindingLabelLeakage")
    _negative_authority(detector_data)
    if (
        detector_data.get("recording_sha256")
        != admission_data.get("recording_sha256")
        or detector_data.get("recording_bytes")
        != admission_data.get("recording_bytes")
        or detector_data.get("frame_count") != admission_data.get("frame_count")
    ):
        raise ValueError("DetectorBindingRecordingMismatch")
    if _utc(detector_data["generated_at_utc"]) >= _utc(
        admission_data.get("prepared_at_utc")
    ):
        raise ValueError("DetectorBindingResultCreatedAfterLabels")
    return (
        admission_data,
        admission,
        admission_signature,
        detector_data,
        binding_fingerprint,
    )


def build_temperature_detector_result_binding_statement(
    recording_path: str | Path,
    detector_result_path: str | Path,
    admission_statement_path: str | Path,
    admission_signature_path: str | Path,
    admission_verifier: Any,
    binding_verifier: Any,
    *,
    prepared_at_utc: str,
    expires_at_utc: str,
    now_utc: str,
) -> bytes:
    """Reverify both artifacts and bind prediction evidence to signed labels."""

    prepared = _utc(prepared_at_utc)
    expires = _utc(expires_at_utc)
    now = _utc(now_utc)
    if expires <= prepared or expires - prepared > MAX_WINDOW:
        raise ValueError("DetectorBindingWindowInvalid")
    if now < prepared or now >= expires:
        raise ValueError("DetectorBindingExpiredOrNotYetValid")
    admission_data, admission, admission_signature, result, fingerprint = _materials(
        recording_path,
        detector_result_path,
        admission_statement_path,
        admission_signature_path,
        admission_verifier,
        binding_verifier,
    )
    statement = {
        "schema": STATEMENT_SCHEMA,
        "namespace": NAMESPACE,
        "scope": SCOPE,
        "key_id": KEY_ID,
        "operator_key_fingerprint": fingerprint,
        "prepared_at_utc": prepared_at_utc,
        "expires_at_utc": expires_at_utc,
        "corpus_id": admission_data["labels"]["corpus_id"],
        "case_id": admission_data["labels"]["case_id"],
        "recording_sha256": result["recording_sha256"],
        "recording_bytes": result["recording_bytes"],
        "frame_count": result["frame_count"],
        "detector_id": result["detector_id"],
        "detector_contract_sha256": result["detector_contract_sha256"],
        "detector_result_sha256": result["result_sha256"],
        "detector_result_generated_at_utc": result["generated_at_utc"],
        "predicted_shared_cooling": result["predicted_shared_cooling"],
        "first_policy_match_index": result["first_policy_match_index"],
        "admission_statement_sha256": _sha256(admission),
        "admission_signature_sha256": _sha256(admission_signature),
        "label_blind_result_precedes_admission": True,
        "eligible_for_statistical_calibration_review": True,
        "field_validated": False,
        "production_validated": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "runtime_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "network_authority": False,
        "automatic_promotion": False,
    }
    return _canonical(statement)


def export_temperature_detector_result_binding_statement(
    recording_path: str | Path,
    detector_result_path: str | Path,
    admission_statement_path: str | Path,
    admission_signature_path: str | Path,
    admission_verifier: Any,
    binding_verifier: Any,
    output_path: str | Path,
    **times: str,
) -> dict[str, Any]:
    """Export the public binding statement without invoking a signer."""

    path = Path(output_path)
    errors: list[str] = []
    statement = b""
    created = False
    try:
        if not path.is_absolute() or path.exists() or path.is_symlink():
            raise ValueError("DetectorBindingOutputUnavailable")
        statement = build_temperature_detector_result_binding_statement(
            recording_path,
            detector_result_path,
            admission_statement_path,
            admission_signature_path,
            admission_verifier,
            binding_verifier,
            **times,
        )
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
        created = True
        try:
            view = memoryview(statement)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("DetectorBindingWriteIncomplete")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except (FileExistsError, FileNotFoundError, OSError, TypeError, ValueError) as error:
        errors.append(str(error) or error.__class__.__name__)
        if created:
            with suppress(OSError):
                path.unlink()
    ready = bool(statement) and not errors
    result = {
        "schema": SCHEMA,
        "status": STATUS_READY if ready else STATUS_HOLD,
        "statement_sha256": _sha256(statement) if ready else None,
        "label_blind_result_bound": ready,
        "binding_signature_verified": False,
        "eligible_for_statistical_calibration_review": False,
        "private_key_accepted": False,
        "signer_invoked": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "errors": errors,
    }
    result["record_sha256"] = _sha256(_canonical(result))
    return result


def evaluate_temperature_detector_result_binding(
    recording_path: str | Path,
    detector_result_path: str | Path,
    admission_statement_path: str | Path,
    admission_signature_path: str | Path,
    admission_verifier: Any,
    binding_verifier: Any,
    binding_statement_path: str | Path,
    binding_signature_path: str | Path | None,
    **times: str,
) -> dict[str, Any]:
    """Reconstruct and authenticate the result binding; perform no corpus write."""

    errors: list[str] = []
    verified = False
    statement_data: dict[str, Any] = {}
    try:
        statement = build_temperature_detector_result_binding_statement(
            recording_path,
            detector_result_path,
            admission_statement_path,
            admission_signature_path,
            admission_verifier,
            binding_verifier,
            **times,
        )
        statement_data = json.loads(statement)
        if _snapshot(Path(binding_statement_path), MAX_PUBLIC_BYTES) != statement:
            raise ValueError("DetectorBindingStatementMismatch")
        if binding_signature_path is None:
            raise ValueError("DetectorBindingSignatureRequired")
        signature = _snapshot(
            Path(binding_signature_path), MAX_SIGNATURE_BYTES
        ).decode("ascii")
        verified = binding_verifier(KEY_ID, statement, signature) is True
        if not verified:
            raise ValueError("DetectorBindingSignatureNotAuthenticated")
    except (
        FileNotFoundError,
        OSError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as error:
        errors.append(str(error) or error.__class__.__name__)
    bound = verified and not errors
    result = {
        "schema": SCHEMA,
        "status": STATUS_BOUND if bound else STATUS_HOLD,
        "case_id": statement_data.get("case_id"),
        "detector_id": statement_data.get("detector_id"),
        "detector_result_sha256": statement_data.get("detector_result_sha256"),
        "predicted_shared_cooling": statement_data.get(
            "predicted_shared_cooling"
        ) if bound else None,
        "first_policy_match_index": statement_data.get(
            "first_policy_match_index"
        ) if bound else None,
        "label_blind_result_bound": bound,
        "binding_signature_verified": verified,
        "eligible_for_statistical_calibration_review": bound,
        "corpus_write_performed": False,
        "field_validated": False,
        "production_validated": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "runtime_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "network_authority": False,
        "automatic_promotion": False,
        "private_key_accepted": False,
        "signer_invoked": False,
        "errors": errors,
    }
    result["record_sha256"] = _sha256(_canonical(result))
    return result


def pending_temperature_detector_result_binding(
    assessment: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose the honest live state before governed predictions exist."""

    characterized = (
        assessment.get("status")
        == "CALIBRATION_CORPUS_CHARACTERIZED_FOR_INDEPENDENT_REVIEW"
    )
    result = {
        "schema": SCHEMA,
        "status": "ACTION_REQUIRED_LABEL_BLIND_DETECTOR_RESULT" if characterized else STATUS_HOLD,
        "label_blind_result_bound": False,
        "binding_signature_verified": False,
        "eligible_for_statistical_calibration_review": False,
        "corpus_write_performed": False,
        "field_validated": False,
        "production_validated": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "next_action": (
            "authenticate and characterize the field corpus"
            if not characterized
            else "replay each recording before labels, then sign the exact result binding offline"
        ),
        "errors": [] if characterized else ["authenticated characterized corpus required"],
    }
    result["record_sha256"] = _sha256(_canonical(result))
    return result


__all__ = [
    "NAMESPACE",
    "STATUS_BOUND",
    "STATUS_HOLD",
    "STATUS_READY",
    "build_temperature_detector_result_binding_statement",
    "evaluate_temperature_detector_result_binding",
    "export_temperature_detector_result_binding_statement",
    "pending_temperature_detector_result_binding",
]
