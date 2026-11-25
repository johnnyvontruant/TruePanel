"""Protected, read-only Black Box intake for the temperature checkride."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from truepanel.history.black_box import MAX_BLACK_BOX_FRAME_BYTES

from .temperature_field_checkride import (
    STATUS_BLOCKED,
    STATUS_HOLD,
    evaluate_temperature_field_checkride,
)

SCHEMA: Final = "truepanel.aegis-temperature-recording-intake/v1"
MAX_RECORDING_BYTES: Final = 4 * MAX_BLACK_BOX_FRAME_BYTES
EXPECTED_FRAME_COUNT: Final = 4


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_protected_recording(path: str | os.PathLike[str]) -> tuple[bytes, list[str]]:
    errors: list[str] = []
    candidate = Path(path)
    if not candidate.is_absolute():
        return b"", ["recording path must be absolute"]
    try:
        if candidate.resolve(strict=True) != candidate:
            return b"", ["recording path must not contain symlinks or aliases"]
    except OSError as error:
        return b"", [f"recording is unavailable: {error.strerror or error}"]

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate, flags)
    except OSError as error:
        return b"", [f"recording could not be opened safely: {error.strerror or error}"]

    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            errors.append("recording must be a regular file")
        if hasattr(os, "getuid") and before.st_uid != os.getuid():
            errors.append("recording must be owned by the current operator")
        if before.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            errors.append("recording must not be group- or world-writable")
        if before.st_size <= 0:
            errors.append("recording must not be empty")
        if before.st_size > MAX_RECORDING_BYTES:
            errors.append("recording exceeds the bounded intake size")

        payload = b""
        if not errors:
            chunks: list[bytes] = []
            remaining = MAX_RECORDING_BYTES + 1
            while remaining > 0:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            if len(payload) > MAX_RECORDING_BYTES:
                errors.append("recording exceeds the bounded intake size")

        after = os.fstat(descriptor)
        try:
            path_after = os.stat(candidate, follow_symlinks=False)
        except OSError:
            errors.append("recording changed while it was read")
        else:
            if _identity(before) != _identity(after) or _identity(after) != _identity(
                path_after
            ):
                errors.append("recording changed while it was read")
    finally:
        os.close(descriptor)

    return payload, list(dict.fromkeys(errors))


def _parse_jsonl(payload: bytes) -> tuple[list[Mapping[str, Any]], list[str]]:
    errors: list[str] = []
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return [], ["recording must be UTF-8 JSONL"]
    lines = text.splitlines()
    if any(not line.strip() for line in lines):
        errors.append("recording must not contain blank frames")
    if len(lines) != EXPECTED_FRAME_COUNT:
        errors.append("recording must contain exactly four JSONL frames")

    frames: list[Mapping[str, Any]] = []
    if not errors:
        for index, line in enumerate(lines):
            if len(line.encode("utf-8")) > MAX_BLACK_BOX_FRAME_BYTES:
                errors.append(f"frame {index} exceeds the Black Box frame limit")
                continue
            try:
                frame = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                errors.append(f"frame {index} is not valid JSON")
                continue
            if not isinstance(frame, Mapping):
                errors.append(f"frame {index} must be a JSON object")
                continue
            frames.append(frame)
    return frames, errors


def pending_temperature_recording_intake(
    field_checkride: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose the honest live state before JT supplies a recording."""

    authenticated = field_checkride.get("operator_signature_verified") is True
    result = {
        "schema": SCHEMA,
        "status": STATUS_HOLD if authenticated else STATUS_BLOCKED,
        "operator_signature_verified": authenticated,
        "recording_present": False,
        "recording_sha256": None,
        "recording_bytes": 0,
        "frame_count": 0,
        "capture_performed": False,
        "private_key_accepted": False,
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
        "next_action": (
            "verify JT's returned development-only SSHSIG"
            if not authenticated
            else "provide one protected four-frame sanitized Black Box recording"
        ),
        "errors": [] if authenticated else ["authenticated development record required"],
    }
    result["record_sha256"] = _sha256(result)
    return result


def evaluate_temperature_recording_intake(
    candidate: Mapping[str, Any],
    appraisal: Mapping[str, Any],
    confirmation: Mapping[str, Any],
    kit_directory: str,
    signature_path: str,
    verifier: Any,
    recording_path: str | os.PathLike[str],
    *,
    now_utc: str,
    evidence_source: str,
    operator_opt_in: bool = False,
    incident_reviewed: bool = False,
) -> dict[str, Any]:
    """Snapshot one protected recording and run the existing checkride.

    The input path is never retained in the returned evidence.  This function
    never captures, tails, deletes, rewrites, or repairs the source file.
    """

    payload, intake_errors = _read_protected_recording(recording_path)
    frames, parse_errors = _parse_jsonl(payload) if payload else ([], [])
    checkride = evaluate_temperature_field_checkride(
        candidate,
        appraisal,
        confirmation,
        kit_directory,
        signature_path,
        verifier,
        frames,
        now_utc=now_utc,
        evidence_source=evidence_source,
        operator_opt_in=operator_opt_in,
        incident_reviewed=incident_reviewed,
    )
    errors = list(
        dict.fromkeys([*intake_errors, *parse_errors, *checkride.get("errors", [])])
    )
    status = STATUS_HOLD if errors else checkride["status"]
    result = {
        "schema": SCHEMA,
        "status": status,
        "operator_signature_verified": checkride.get("operator_signature_verified")
        is True,
        "development_authentication_record_sha256": checkride.get(
            "authentication_record_sha256"
        ),
        "recording_present": bool(payload),
        "recording_sha256": hashlib.sha256(payload).hexdigest() if payload else None,
        "recording_bytes": len(payload),
        "frame_count": len(frames),
        "observation_source": evidence_source,
        "fault_detected": checkride.get("fault_detected") is True,
        "stable_member_identity": checkride.get("stable_member_identity") is True,
        "recovery_verified": checkride.get("recovery_verified") is True,
        "eligible_for_calibration_review": (
            not errors and checkride.get("eligible_for_calibration_review") is True
        ),
        "capture_performed": False,
        "private_key_accepted": False,
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
        "errors": errors,
    }
    result["record_sha256"] = _sha256(result)
    return result


__all__ = [
    "MAX_RECORDING_BYTES",
    "evaluate_temperature_recording_intake",
    "pending_temperature_recording_intake",
]
