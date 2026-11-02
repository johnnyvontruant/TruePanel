"""Append-only import of authenticated temperature calibration cases."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import stat
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any, Final

from .ssh_verifier import MAX_SIGNATURE_BYTES
from .temperature_calibration_admission import (
    MAX_PUBLIC_BYTES,
    STATUS_ADMITTED,
    _snapshot,
    build_temperature_calibration_admission_statement,
    evaluate_temperature_calibration_admission,
)
from .temperature_recording_intake import (
    MAX_RECORDING_BYTES,
    _parse_jsonl,
    _read_protected_recording,
)

SCHEMA: Final = "truepanel.aegis-temperature-calibration-corpus-import/v1"
CORPUS_SCHEMA: Final = "truepanel.aegis-temperature-calibration-corpus/v1"
STATUS_IMPORTED: Final = "CALIBRATION_CASE_IMPORTED_FOR_OFFLINE_ANALYSIS"
STATUS_HOLD: Final = "HOLD"
MAX_CASES: Final = 256


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_complete(path: Path, payload: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("CalibrationCorpusWriteIncomplete")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _safe_root(path: str | Path, corpus_id: str) -> tuple[Path, bool]:
    root = Path(path)
    if (
        not root.is_absolute()
        or root.is_symlink()
        or root.parent.resolve(strict=True) != root.parent
    ):
        raise ValueError("CalibrationCorpusRootInvalid")
    created = False
    if not root.exists():
        root.mkdir(mode=0o700)
        created = True
    resolved = root.resolve(strict=True)
    if resolved != root:
        raise ValueError("CalibrationCorpusRootInvalid")
    metadata = root.stat(follow_symlinks=False)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o077
    ):
        raise ValueError("CalibrationCorpusRootUnsafe")
    cases = root / "cases"
    meta = root / "corpus.json"
    if created:
        cases.mkdir(mode=0o700)
        _write_complete(
            meta,
            _canonical(
                {
                    "schema": CORPUS_SCHEMA,
                    "corpus_id": corpus_id,
                    "storage": "append-only-case-directories",
                    "field_validated": False,
                    "production_validated": False,
                    "deployment_authority": False,
                    "hardware_authority": False,
                }
            )
            + b"\n",
        )
    else:
        if cases.is_symlink() or not cases.is_dir() or meta.is_symlink():
            raise ValueError("CalibrationCorpusLayoutInvalid")
        cases_metadata = cases.stat(follow_symlinks=False)
        meta_metadata = meta.stat(follow_symlinks=False)
        if (
            cases_metadata.st_uid != os.geteuid()
            or cases_metadata.st_mode & 0o077
            or not stat.S_ISREG(meta_metadata.st_mode)
            or meta_metadata.st_uid != os.geteuid()
            or meta_metadata.st_mode & 0o077
        ):
            raise ValueError("CalibrationCorpusLayoutUnsafe")
        stored = json.loads(meta.read_text(encoding="utf-8"))
        if set(stored) != {
            "schema",
            "corpus_id",
            "storage",
            "field_validated",
            "production_validated",
            "deployment_authority",
            "hardware_authority",
        } or stored != {
            "schema": CORPUS_SCHEMA,
            "corpus_id": corpus_id,
            "storage": "append-only-case-directories",
            "field_validated": False,
            "production_validated": False,
            "deployment_authority": False,
            "hardware_authority": False,
        }:
            raise ValueError("CalibrationCorpusMetadataMismatch")
    return root, created


def _case_receipts(cases: Path) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for entry in sorted(cases.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_symlink() or not entry.is_dir():
            raise ValueError("CalibrationCorpusUnexpectedEntry")
        entry_metadata = entry.stat(follow_symlinks=False)
        if entry_metadata.st_uid != os.geteuid() or entry_metadata.st_mode & 0o077:
            raise ValueError("CalibrationCorpusCaseUnsafe")
        expected_names = {
            "recording.jsonl",
            "admission-statement.json",
            "admission-signature.sshsig",
            "import-receipt.json",
        }
        if {item.name for item in entry.iterdir()} != expected_names:
            raise ValueError("CalibrationCorpusCaseShapeInvalid")
        for item in entry.iterdir():
            metadata = item.stat(follow_symlinks=False)
            if (
                item.is_symlink()
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or metadata.st_mode & 0o077
            ):
                raise ValueError("CalibrationCorpusCaseFileUnsafe")
        receipt_path = entry / "import-receipt.json"
        if receipt_path.is_symlink():
            raise ValueError("CalibrationCorpusReceiptInvalid")
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as error:
            raise ValueError("CalibrationCorpusReceiptInvalid") from error
        if receipt.get("case_id") != entry.name:
            raise ValueError("CalibrationCorpusReceiptCaseMismatch")
        expected = receipt.get("receipt_sha256")
        unsigned = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        if expected != _sha256(_canonical(unsigned)):
            raise ValueError("CalibrationCorpusReceiptDigestMismatch")
        recording = (entry / "recording.jsonl").read_bytes()
        statement = (entry / "admission-statement.json").read_bytes()
        signature = (entry / "admission-signature.sshsig").read_bytes()
        if (
            _sha256(recording) != receipt.get("recording_sha256")
            or len(recording) != receipt.get("recording_bytes")
            or _sha256(statement) != receipt.get("admission_statement_sha256")
            or _sha256(signature) != receipt.get("admission_signature_sha256")
            or len(signature) != receipt.get("admission_signature_bytes")
        ):
            raise ValueError("CalibrationCorpusCaseArtifactMismatch")
        receipts.append(receipt)
    return receipts


def import_temperature_calibration_case(
    field_review_arguments: Mapping[str, Any],
    labels: Mapping[str, Any],
    admission_verifier: Any,
    statement_path: str | Path,
    signature_path: str | Path | None,
    corpus_path: str | Path,
    *,
    prepared_at_utc: str,
    expires_at_utc: str,
    now_utc: str,
) -> dict[str, Any]:
    """Re-verify one admission and atomically append its exact evidence."""

    errors: list[str] = []
    imported = False
    created_root = False
    case_count = 0
    recording_sha256: str | None = None
    case_id: str | None = None
    receipt_sha256: str | None = None
    try:
        admission = evaluate_temperature_calibration_admission(
            field_review_arguments,
            labels,
            admission_verifier,
            statement_path,
            signature_path,
            prepared_at_utc=prepared_at_utc,
            expires_at_utc=expires_at_utc,
            now_utc=now_utc,
        )
        if admission.get("status") != STATUS_ADMITTED:
            raise ValueError("CalibrationCorpusAdmissionNotAuthenticated")
        normalized = admission["labels"]
        case_id = normalized["case_id"]
        recording_sha256 = admission["recording_sha256"]
        recording_path = field_review_arguments.get("recording_path")
        payload, intake_errors = _read_protected_recording(recording_path)
        frames, parse_errors = _parse_jsonl(payload) if payload else ([], [])
        if intake_errors or parse_errors:
            raise ValueError("CalibrationCorpusRecordingInvalid")
        expected_statement = build_temperature_calibration_admission_statement(
            field_review_arguments,
            labels,
            admission_verifier,
            prepared_at_utc=prepared_at_utc,
            expires_at_utc=expires_at_utc,
            now_utc=now_utc,
        )
        statement = _snapshot(Path(statement_path), MAX_PUBLIC_BYTES)
        if statement != expected_statement:
            raise ValueError("CalibrationCorpusAdmissionStatementChanged")
        statement_data = json.loads(statement)
        if (
            _sha256(payload) != recording_sha256
            or len(payload) != statement_data.get("recording_bytes")
            or len(frames) != statement_data.get("frame_count")
            or len(frames) != 4
        ):
            raise ValueError("CalibrationCorpusRecordingMismatch")
        if len(statement) > MAX_PUBLIC_BYTES or len(payload) > MAX_RECORDING_BYTES:
            raise ValueError("CalibrationCorpusArtifactTooLarge")
        if signature_path is None:
            raise ValueError("CalibrationCorpusAdmissionSignatureRequired")
        signature = _snapshot(Path(signature_path), MAX_SIGNATURE_BYTES)

        root, created_root = _safe_root(corpus_path, normalized["corpus_id"])
        lock_path = root / ".import.lock"
        lock_descriptor = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
            receipts = _case_receipts(root / "cases")
            case_count = len(receipts)
            if case_count >= MAX_CASES:
                raise ValueError("CalibrationCorpusCaseLimitExceeded")
            if any(item["case_id"] == case_id for item in receipts):
                raise ValueError("CalibrationCorpusCaseDuplicate")
            if any(item["recording_sha256"] == recording_sha256 for item in receipts):
                raise ValueError("CalibrationCorpusRecordingDuplicate")

            unsigned_receipt = {
                "schema": SCHEMA,
                "corpus_id": normalized["corpus_id"],
                "case_id": case_id,
                "recording_sha256": recording_sha256,
                "recording_bytes": len(payload),
                "frame_count": len(frames),
                "admission_record_sha256": admission["record_sha256"],
                "admission_statement_sha256": _sha256(statement),
                "admission_signature_sha256": _sha256(signature),
                "admission_signature_bytes": len(signature),
                "labels": normalized,
                "imported_for_offline_analysis": True,
                "field_validated": False,
                "production_validated": False,
                "candidate_accepted": False,
                "candidate_installed": False,
                "runtime_authority": False,
                "deployment_authority": False,
                "hardware_authority": False,
                "automatic_promotion": False,
            }
            receipt_sha256 = _sha256(_canonical(unsigned_receipt))
            receipt = {**unsigned_receipt, "receipt_sha256": receipt_sha256}
            temporary = Path(
                tempfile.mkdtemp(prefix=".import-", dir=root / "cases")
            )
            os.chmod(temporary, 0o700)
            try:
                _write_complete(temporary / "recording.jsonl", payload)
                _write_complete(temporary / "admission-statement.json", statement)
                _write_complete(temporary / "admission-signature.sshsig", signature)
                _write_complete(
                    temporary / "import-receipt.json",
                    _canonical(receipt) + b"\n",
                )
                os.replace(temporary, root / "cases" / case_id)
                directory = os.open(root / "cases", os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
                imported = True
                case_count += 1
            finally:
                with suppress(FileNotFoundError):
                    shutil.rmtree(temporary)
        finally:
            os.close(lock_descriptor)
    except (FileExistsError, FileNotFoundError, OSError, TypeError, ValueError) as error:
        errors.append(str(error) or error.__class__.__name__)
        if created_root and not imported:
            with suppress(OSError):
                shutil.rmtree(Path(corpus_path))

    result = {
        "schema": SCHEMA,
        "status": STATUS_IMPORTED if imported else STATUS_HOLD,
        "case_id": case_id,
        "recording_sha256": recording_sha256,
        "import_receipt_sha256": receipt_sha256 if imported else None,
        "case_count": case_count,
        "admission_reverified": imported,
        "corpus_write_performed": imported,
        "append_only_commit": imported,
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


def pending_temperature_calibration_corpus_import(
    admission: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose the honest live state before an authenticated import exists."""

    eligible = admission.get("eligible_for_corpus_import") is True
    result = {
        "schema": SCHEMA,
        "status": "ACTION_REQUIRED_AUTHENTICATED_CORPUS_IMPORT" if eligible else STATUS_HOLD,
        "admission_reverified": False,
        "corpus_write_performed": False,
        "append_only_commit": False,
        "case_count": 0,
        "field_validated": False,
        "production_validated": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "next_action": (
            "authenticate the exact calibration admission"
            if not eligible
            else "import the exact reviewed recording into the append-only offline corpus"
        ),
        "errors": [] if eligible else ["authenticated calibration admission required"],
    }
    result["record_sha256"] = _sha256(_canonical(result))
    return result


__all__ = [
    "STATUS_HOLD",
    "STATUS_IMPORTED",
    "import_temperature_calibration_case",
    "pending_temperature_calibration_corpus_import",
]
