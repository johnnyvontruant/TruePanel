"""Content-bound admission of one reviewed temperature case to calibration."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from .ssh_verifier import MAX_ALLOWED_SIGNERS_BYTES, validate_allowed_signers_roster
from .temperature_authenticated_acceptance import KEY_ID
from .temperature_field_review_receipt import (
    MAX_SIGNATURE_BYTES,
    evaluate_temperature_field_review_receipt,
)
from .temperature_field_review_receipt import (
    NAMESPACE as FIELD_REVIEW_NAMESPACE,
)

SCHEMA: Final = "truepanel.aegis-temperature-calibration-admission/v1"
STATEMENT_SCHEMA: Final = (
    "truepanel.aegis-temperature-calibration-admission-statement/v1"
)
NAMESPACE: Final = "truepanel-aegis-temperature-calibration-admission-v1@truepanel"
SCOPE: Final = "temperature-calibration-corpus-import-only"
STATUS_READY: Final = "READY_FOR_OFFLINE_CALIBRATION_ADMISSION_SIGNATURE"
STATUS_ADMITTED: Final = "CALIBRATION_CASE_AUTHENTICATED_FOR_CORPUS_IMPORT"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_CALIBRATION_ADMISSION_SIGNATURE"
STATUS_HOLD: Final = "HOLD"
MAX_WINDOW: Final = timedelta(hours=2)
MAX_PUBLIC_BYTES: Final = 128 * 1024
_SAFE_ID: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _record_sha256(value: Any) -> str:
    return _sha256(_canonical(value))


def _utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("CalibrationAdmissionTimeInvalid")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC:
        raise ValueError("CalibrationAdmissionTimeInvalid")
    return parsed


def _window(prepared_at_utc: str, expires_at_utc: str, now_utc: str) -> None:
    prepared = _utc(prepared_at_utc)
    expires = _utc(expires_at_utc)
    now = _utc(now_utc)
    if expires <= prepared or expires - prepared > MAX_WINDOW:
        raise ValueError("CalibrationAdmissionWindowInvalid")
    if now < prepared or now >= expires:
        raise ValueError("CalibrationAdmissionExpiredOrNotYetValid")


def _snapshot(path: Path, maximum: int) -> bytes:
    if not path.is_absolute() or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("ProtectedAdmissionFileUnavailable")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_mode & 0o022
        ):
            raise ValueError("ProtectedAdmissionFileInvalid")
        if before.st_size <= 0 or before.st_size > maximum:
            raise ValueError("ProtectedAdmissionFileSizeInvalid")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        identity = lambda item: (  # noqa: E731
            item.st_dev,
            item.st_ino,
            item.st_mode,
            item.st_uid,
            item.st_size,
            item.st_mtime_ns,
            item.st_ctime_ns,
        )
        if identity(before) != identity(after) or len(payload) > maximum:
            raise ValueError("ProtectedAdmissionFileChanged")
        return payload
    finally:
        os.close(descriptor)


def _fingerprint(verifier: Any, namespace: str) -> tuple[Path, str]:
    if (
        getattr(verifier, "namespace", None) != namespace
        or getattr(verifier, "expected_key_ids", None) != (KEY_ID,)
    ):
        raise ValueError("CalibrationAdmissionVerifierPolicyMismatch")
    path = getattr(verifier, "allowed_signers_path", None)
    if not isinstance(path, Path):
        raise ValueError("CalibrationAdmissionVerifierPolicyMismatch")
    roster = validate_allowed_signers_roster(
        _snapshot(path, MAX_ALLOWED_SIGNERS_BYTES), expected_key_ids=(KEY_ID,)
    )
    return path.resolve(strict=True), roster[KEY_ID]


def _labels(labels: Mapping[str, Any]) -> dict[str, Any]:
    required = ("corpus_id", "case_id", "challenge", "system_profile", "workload_class")
    for name in required:
        value = labels.get(name)
        if name in {"corpus_id", "case_id"}:
            if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
                raise ValueError(f"CalibrationAdmission{name.title().replace('_', '')}Invalid")
        elif not isinstance(value, str) or not value.strip():
            raise ValueError(f"CalibrationAdmission{name.title().replace('_', '')}Required")
    if type(labels.get("expected_shared_cooling")) is not bool:
        raise ValueError("CalibrationAdmissionOutcomeLabelRequired")
    threshold = labels.get("first_isolated_threshold_index")
    if threshold is not None and (type(threshold) is not int or threshold < 0):
        raise ValueError("CalibrationAdmissionThresholdIndexInvalid")
    if set(labels) != {
        *required,
        "expected_shared_cooling",
        "first_isolated_threshold_index",
    }:
        raise ValueError("CalibrationAdmissionLabelsShapeInvalid")
    return {
        "corpus_id": labels["corpus_id"],
        "case_id": labels["case_id"],
        "challenge": labels["challenge"].strip(),
        "system_profile": labels["system_profile"].strip(),
        "workload_class": labels["workload_class"].strip(),
        "expected_shared_cooling": labels["expected_shared_cooling"],
        "first_isolated_threshold_index": threshold,
    }


def build_temperature_calibration_admission_statement(
    field_review_arguments: Mapping[str, Any],
    labels: Mapping[str, Any],
    admission_verifier: Any,
    *,
    prepared_at_utc: str,
    expires_at_utc: str,
    now_utc: str,
) -> bytes:
    """Rebuild the signed field receipt, then bind its exact corpus labels."""

    _window(prepared_at_utc, expires_at_utc, now_utc)
    field_receipt = evaluate_temperature_field_review_receipt(**field_review_arguments)
    if field_receipt.get("status") != "FIELD_OBSERVATION_ACCEPTED_FOR_REVIEW":
        raise ValueError("CalibrationAdmissionFieldReviewNotAccepted")
    review_verifier = field_review_arguments.get("review_verifier")
    review_path, review_fingerprint = _fingerprint(
        review_verifier, FIELD_REVIEW_NAMESPACE
    )
    admission_path, admission_fingerprint = _fingerprint(admission_verifier, NAMESPACE)
    if review_path != admission_path or review_fingerprint != admission_fingerprint:
        raise ValueError("CalibrationAdmissionTrustRootMismatch")
    normalized = _labels(labels)
    statement = {
        "schema": STATEMENT_SCHEMA,
        "namespace": NAMESPACE,
        "scope": SCOPE,
        "key_id": KEY_ID,
        "operator_key_fingerprint": admission_fingerprint,
        "prepared_at_utc": prepared_at_utc,
        "expires_at_utc": expires_at_utc,
        "field_review_receipt_sha256": field_receipt["record_sha256"],
        "field_review_statement_sha256": field_receipt["review_statement_sha256"],
        "recording_sha256": field_receipt["recording_sha256"],
        "recording_bytes": field_receipt["recording_bytes"],
        "frame_count": field_receipt["frame_count"],
        "labels": normalized,
        "label_statement": (
            "I confirm these labels describe the reviewed incident outcome for "
            "calibration corpus import only."
        ),
        "eligible_for_corpus_import": True,
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


def export_temperature_calibration_admission_statement(
    field_review_arguments: Mapping[str, Any],
    labels: Mapping[str, Any],
    admission_verifier: Any,
    output_path: str | Path,
    *,
    prepared_at_utc: str,
    expires_at_utc: str,
    now_utc: str,
) -> dict[str, Any]:
    """Create one public statement without accepting or invoking a private key."""

    errors: list[str] = []
    statement = b""
    created = False
    path = Path(output_path)
    try:
        if not path.is_absolute() or path.exists() or path.is_symlink():
            raise ValueError("CalibrationAdmissionOutputUnavailable")
        statement = build_temperature_calibration_admission_statement(
            field_review_arguments,
            labels,
            admission_verifier,
            prepared_at_utc=prepared_at_utc,
            expires_at_utc=expires_at_utc,
            now_utc=now_utc,
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
                    raise OSError("CalibrationAdmissionWriteFailed")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except (FileExistsError, FileNotFoundError, OSError, TypeError, ValueError) as error:
        errors.append(str(error) or error.__class__.__name__)
        if created:
            with suppress(OSError):
                path.unlink()
    ready = not errors
    result = {
        "schema": SCHEMA,
        "status": STATUS_READY if ready else STATUS_HOLD,
        "statement_created": ready,
        "statement_sha256": _sha256(statement) if statement else None,
        "private_key_accepted": False,
        "signer_invoked": False,
        "eligible_for_corpus_import": False,
        "field_validated": False,
        "candidate_installed": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "errors": errors,
    }
    result["record_sha256"] = _record_sha256(result)
    return result


def evaluate_temperature_calibration_admission(
    field_review_arguments: Mapping[str, Any],
    labels: Mapping[str, Any],
    admission_verifier: Any,
    statement_path: str | Path,
    signature_path: str | Path | None,
    *,
    prepared_at_utc: str,
    expires_at_utc: str,
    now_utc: str,
) -> dict[str, Any]:
    """Authenticate exact labels for import; perform no corpus or runtime write."""

    errors: list[str] = []
    signature_verified = False
    statement = b""
    statement_data: dict[str, Any] = {}
    try:
        statement = build_temperature_calibration_admission_statement(
            field_review_arguments,
            labels,
            admission_verifier,
            prepared_at_utc=prepared_at_utc,
            expires_at_utc=expires_at_utc,
            now_utc=now_utc,
        )
        statement_data = json.loads(statement)
        if _snapshot(Path(statement_path), MAX_PUBLIC_BYTES) != statement:
            raise ValueError("CalibrationAdmissionStatementMismatch")
        if signature_path is None:
            raise ValueError("CalibrationAdmissionSignatureRequired")
        signature = _snapshot(Path(signature_path), MAX_SIGNATURE_BYTES).decode("ascii")
        signature_verified = admission_verifier(KEY_ID, statement, signature) is True
        if not signature_verified:
            raise ValueError("CalibrationAdmissionSignatureNotAuthenticated")
    except (
        FileNotFoundError,
        OSError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as error:
        errors.append(str(error) or error.__class__.__name__)
    admitted = not errors and signature_verified
    result = {
        "schema": SCHEMA,
        "status": STATUS_ADMITTED if admitted else STATUS_HOLD,
        "key_id": KEY_ID,
        "namespace": NAMESPACE,
        "scope": SCOPE,
        "admission_signature_verified": signature_verified,
        "field_review_receipt_sha256": statement_data.get(
            "field_review_receipt_sha256"
        ),
        "recording_sha256": statement_data.get("recording_sha256"),
        "labels": statement_data.get("labels") if admitted else None,
        "eligible_for_corpus_import": admitted,
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
    result["record_sha256"] = _record_sha256(result)
    return result


def pending_temperature_calibration_admission(
    field_review_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose the live gate without fabricating labels or operator signatures."""

    review_verified = field_review_receipt.get("operator_review_signature_verified") is True
    result = {
        "schema": SCHEMA,
        "status": STATUS_REQUIRED if review_verified else STATUS_HOLD,
        "field_review_verified": review_verified,
        "labels_bound": False,
        "admission_signature_verified": False,
        "eligible_for_corpus_import": False,
        "corpus_write_performed": False,
        "field_validated": False,
        "production_validated": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "next_action": (
            "complete the content-bound field review receipt"
            if not review_verified
            else "bind the exact incident labels and sign the admission statement offline"
        ),
        "errors": [] if review_verified else ["authenticated field review required"],
    }
    result["record_sha256"] = _record_sha256(result)
    return result


__all__ = [
    "NAMESPACE",
    "STATUS_ADMITTED",
    "STATUS_HOLD",
    "STATUS_READY",
    "build_temperature_calibration_admission_statement",
    "evaluate_temperature_calibration_admission",
    "export_temperature_calibration_admission_statement",
    "pending_temperature_calibration_admission",
]
