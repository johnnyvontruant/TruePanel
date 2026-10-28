"""Governed, read-only Black Box intake for correlation calibration."""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from truepanel.history.black_box import (
    MAX_BLACK_BOX_FRAME_BYTES,
    MAX_BLACK_BOX_REPLAY_FRAMES,
    BlackBoxFrame,
)

SCHEMA: Final = "truepanel.aegis-temperature-long-window-intake/v1"
STATUS_READY: Final = "LONG_WINDOW_RECORDING_ACCEPTED_FOR_LABEL_BLIND_REPLAY"
STATUS_HOLD: Final = "HOLD"
MIN_FRAME_COUNT: Final = 24
MIN_BASELINE_FRAMES: Final = 12
MAX_FRAME_COUNT: Final = MAX_BLACK_BOX_REPLAY_FRAMES
MAX_RECORDING_BYTES: Final = 16 * 1024 * 1024
REQUIRED_METRICS: Final = (
    "fan.pwm",
    "fan.rpm",
    "drive.temperature_c",
    "cpu.temperature_c",
)
_BASELINE_MAX_RANGES: Final = {
    "fan.pwm": 20.0,
    "fan.rpm": 200.0,
    "drive.temperature_c": 2.0,
    "cpu.temperature_c": 5.0,
}
_FORBIDDEN_LABEL_KEYS: Final = {
    "label",
    "labels",
    "ground_truth",
    "outcome",
    "expected_shared_cooling",
    "first_isolated_threshold_index",
}


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


def _read_once(path: str | os.PathLike[str]) -> tuple[bytes, list[str]]:
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

    errors: list[str] = []
    payload = b""
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
            errors.append("recording exceeds the long-window intake size")

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
                errors.append("recording exceeds the long-window intake size")

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


def _contains_labels(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in _FORBIDDEN_LABEL_KEYS or _contains_labels(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_labels(item) for item in value)
    return False


def _parse(payload: bytes) -> tuple[list[BlackBoxFrame], list[str]]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return [], ["recording must be UTF-8 JSONL"]
    lines = text.splitlines()
    errors: list[str] = []
    if any(not line.strip() for line in lines):
        errors.append("recording must not contain blank frames")
    if len(lines) < MIN_FRAME_COUNT:
        errors.append(f"recording requires at least {MIN_FRAME_COUNT} frames")
    if len(lines) > MAX_FRAME_COUNT:
        errors.append(f"recording exceeds the {MAX_FRAME_COUNT}-frame replay limit")

    frames: list[BlackBoxFrame] = []
    if not errors:
        for index, line in enumerate(lines):
            encoded = line.encode("utf-8")
            if len(encoded) > MAX_BLACK_BOX_FRAME_BYTES:
                errors.append(f"frame {index} exceeds the Black Box frame limit")
                continue
            try:
                raw = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                errors.append(f"frame {index} is not valid JSON")
                continue
            if not isinstance(raw, Mapping):
                errors.append(f"frame {index} must be a JSON object")
                continue
            if _contains_labels(raw):
                errors.append(f"frame {index} contains calibration labels")
                continue
            try:
                frame = BlackBoxFrame.from_dict(raw)
            except (KeyError, TypeError, ValueError) as error:
                errors.append(f"frame {index} violates the Black Box contract: {error}")
                continue
            if frame.as_dict() != raw:
                errors.append(f"frame {index} is not canonical sanitized Black Box data")
                continue
            frames.append(frame)

    if errors:
        return frames, list(dict.fromkeys(errors))

    for index, frame in enumerate(frames):
        if index and frame.sequence != frames[index - 1].sequence + 1:
            errors.append("frame sequence must increase by exactly one")
        if index and frame.captured_at <= frames[index - 1].captured_at:
            errors.append("capture timestamps must increase monotonically")
        metrics = frame.telemetry.get("metrics")
        if not isinstance(metrics, Mapping):
            errors.append(f"frame {index} requires telemetry metrics")
            continue
        for metric in REQUIRED_METRICS:
            value = metrics.get(metric)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(f"frame {index} requires numeric {metric}")
            elif not math.isfinite(float(value)):
                errors.append(f"frame {index} requires finite {metric}")

    if not errors:
        baseline = frames[:MIN_BASELINE_FRAMES]
        for metric, maximum_range in _BASELINE_MAX_RANGES.items():
            values = [float(frame.telemetry["metrics"][metric]) for frame in baseline]
            if max(values) - min(values) > maximum_range:
                errors.append(f"baseline is unstable for {metric}")
    return frames, list(dict.fromkeys(errors))


def pending_temperature_long_window_intake(
    calibration_assessment: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose the unambiguous no-recording state in Mission Control."""

    characterized = (
        calibration_assessment.get("status")
        == "CALIBRATION_CORPUS_CHARACTERIZED_FOR_INDEPENDENT_REVIEW"
    )
    result = {
        "schema": SCHEMA,
        "status": "ACTION_REQUIRED_LONG_WINDOW_RECORDING" if characterized else STATUS_HOLD,
        "calibration_assessment_ready": characterized,
        "recording_present": False,
        "recording_sha256": None,
        "recording_bytes": 0,
        "frame_count": 0,
        "baseline_frame_count": 0,
        "baseline_stable": False,
        "labels_present": False,
        "eligible_for_label_blind_replay": False,
        "capture_performed": False,
        "tailing_performed": False,
        "checkpoint_write_performed": False,
        "field_validated": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "runtime_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "network_authority": False,
        "automatic_promotion": False,
        "next_action": (
            "characterize the authenticated calibration corpus"
            if not characterized
            else "provide one protected sanitized long-window Black Box recording"
        ),
        "errors": [] if characterized else ["characterized calibration corpus required"],
    }
    result["record_sha256"] = _sha256(result)
    return result


def evaluate_temperature_long_window_intake(
    recording_path: str | os.PathLike[str],
) -> dict[str, Any]:
    """Validate one immutable snapshot without capture, tailing, or labels."""

    payload, read_errors = _read_once(recording_path)
    frames, parse_errors = _parse(payload) if payload else ([], [])
    errors = list(dict.fromkeys([*read_errors, *parse_errors]))
    result = {
        "schema": SCHEMA,
        "status": STATUS_HOLD if errors else STATUS_READY,
        "recording_present": bool(payload),
        "recording_sha256": hashlib.sha256(payload).hexdigest() if payload else None,
        "recording_bytes": len(payload),
        "frame_count": len(frames),
        "first_sequence": frames[0].sequence if frames else None,
        "last_sequence": frames[-1].sequence if frames else None,
        "first_captured_at": frames[0].captured_at if frames else None,
        "last_captured_at": frames[-1].captured_at if frames else None,
        "baseline_frame_count": MIN_BASELINE_FRAMES if not errors else 0,
        "baseline_stable": not errors,
        "labels_present": any("calibration labels" in error for error in errors),
        "eligible_for_label_blind_replay": not errors,
        "capture_performed": False,
        "tailing_performed": False,
        "checkpoint_write_performed": False,
        "field_validated": False,
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
    "MIN_BASELINE_FRAMES",
    "MIN_FRAME_COUNT",
    "evaluate_temperature_long_window_intake",
    "pending_temperature_long_window_intake",
]
