"""Label-blind detector results bound to one protected Black Box recording."""

from __future__ import annotations

import hashlib
import json
import math
import os
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any, Final

from truepanel.history.black_box import BlackBoxFrame
from truepanel.oracle import OracleEngine

from .correlation import correlate_incident
from .policy import DEFAULT_CORRELATION_POLICY
from .temperature_recording_intake import _read_protected_recording

SCHEMA: Final = "truepanel.aegis-temperature-detector-result/v1"
DETECTOR_ID: Final = "aegis-declarative-correlation-v1"
STATUS_READY: Final = "LABEL_BLIND_DETECTOR_RESULT_BOUND"
STATUS_HOLD: Final = "HOLD"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("DetectorResultTimeInvalid")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC:
        raise ValueError("DetectorResultTimeInvalid")
    return parsed


def _parse_frames(payload: bytes) -> list[BlackBoxFrame]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("DetectorResultRecordingInvalid") from error
    if not lines or len(lines) > 10_000 or any(not line.strip() for line in lines):
        raise ValueError("DetectorResultFrameCountInvalid")
    frames: list[BlackBoxFrame] = []
    for line in lines:
        try:
            raw = json.loads(line)
            frame = BlackBoxFrame.from_dict(raw)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("DetectorResultRecordingInvalid") from error
        if raw != frame.as_dict():
            raise ValueError("DetectorResultRecordingNotSanitizedAtRest")
        frames.append(frame)
    if any(
        current.sequence <= previous.sequence
        or current.captured_at <= previous.captured_at
        for previous, current in zip(frames, frames[1:], strict=False)
    ):
        raise ValueError("DetectorResultRecordingOrderInvalid")
    return frames


def build_temperature_detector_result(
    recording_path: str | Path,
    *,
    generated_at_utc: str,
) -> dict[str, Any]:
    """Replay without labels and return a deterministic, content-addressed result."""

    _utc(generated_at_utc)
    payload, errors = _read_protected_recording(recording_path)
    if errors:
        raise ValueError("DetectorResultRecordingUnavailable")
    frames = _parse_frames(payload)
    oracle = OracleEngine()
    match_indices: list[int] = []
    confidences: list[float] = []
    evidence: list[dict[str, Any]] = []
    for index, frame in enumerate(frames):
        telemetry = frame.telemetry
        outlook = oracle.observe(
            timestamp=frame.captured_at,
            metrics=telemetry.get("metrics", telemetry),
            hard_faults=tuple(telemetry.get("hard_faults", ())),
        )
        incident = correlate_incident([], outlook)
        if incident and incident.get("incident_id") == "aegis:shared-cooling":
            confidence = float(incident.get("confidence"))
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError("DetectorResultConfidenceInvalid")
            match_indices.append(index)
            confidences.append(confidence)
            evidence.append(
                {
                    "frame_index": index,
                    "confidence": confidence,
                    "matched_evidence": list(
                        incident.get("confidence_basis", {}).get(
                            "matched_evidence", ()
                        )
                    ),
                }
            )
    policy = DEFAULT_CORRELATION_POLICY.describe()
    result = {
        "schema": SCHEMA,
        "status": STATUS_READY,
        "generated_at_utc": generated_at_utc,
        "recording_sha256": _sha256(payload),
        "recording_bytes": len(payload),
        "frame_count": len(frames),
        "detector_id": DETECTOR_ID,
        "detector_contract_sha256": _sha256(
            _canonical(
                {
                    "detector_id": DETECTOR_ID,
                    "policy": policy,
                    "oracle_contract": "truepanel-oracle-v1",
                    "result_schema": SCHEMA,
                }
            )
        ),
        "predicted_shared_cooling": bool(match_indices),
        "first_policy_match_index": match_indices[0] if match_indices else None,
        "incident_frame_count": len(match_indices),
        "confidence_mean": round(fmean(confidences), 3) if confidences else None,
        "evidence": evidence,
        "label_blind": True,
        "labels_present": False,
        "read_only_replay": True,
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
    result["result_sha256"] = _sha256(_canonical(result))
    return result


def export_temperature_detector_result(
    recording_path: str | Path,
    output_path: str | Path,
    *,
    generated_at_utc: str,
) -> dict[str, Any]:
    """Atomically export one public result; never accept labels or a signer."""

    path = Path(output_path)
    created = False
    errors: list[str] = []
    result: dict[str, Any] | None = None
    try:
        if not path.is_absolute() or path.exists() or path.is_symlink():
            raise ValueError("DetectorResultOutputUnavailable")
        result = build_temperature_detector_result(
            recording_path, generated_at_utc=generated_at_utc
        )
        payload = _canonical(result) + b"\n"
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
        created = True
        try:
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("DetectorResultWriteIncomplete")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except (FileExistsError, FileNotFoundError, OSError, TypeError, ValueError) as error:
        errors.append(str(error) or error.__class__.__name__)
        if created:
            with suppress(OSError):
                path.unlink()
    exported = result is not None and not errors
    return {
        "schema": SCHEMA,
        "status": STATUS_READY if exported else STATUS_HOLD,
        "result_sha256": result.get("result_sha256") if exported else None,
        "predicted_shared_cooling": (
            result.get("predicted_shared_cooling") if exported else None
        ),
        "first_policy_match_index": (
            result.get("first_policy_match_index") if exported else None
        ),
        "label_blind": exported,
        "labels_accepted": False,
        "private_key_accepted": False,
        "signer_invoked": False,
        "errors": errors,
    }


__all__ = [
    "DETECTOR_ID",
    "SCHEMA",
    "STATUS_HOLD",
    "STATUS_READY",
    "build_temperature_detector_result",
    "export_temperature_detector_result",
]
