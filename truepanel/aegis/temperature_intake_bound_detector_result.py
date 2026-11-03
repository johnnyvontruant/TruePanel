"""Detector results bound to a reconstructed governed long-window receipt."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any, Final

from .temperature_calibration_admission import _snapshot
from .temperature_detector_result import build_temperature_detector_result
from .temperature_long_window_intake import (
    SCHEMA as INTAKE_SCHEMA,
)
from .temperature_long_window_intake import (
    STATUS_READY as INTAKE_READY,
)
from .temperature_long_window_intake import (
    evaluate_temperature_long_window_intake,
)

SCHEMA: Final = "truepanel.aegis-temperature-intake-bound-detector-result/v1"
STATUS_READY: Final = "INTAKE_BOUND_DETECTOR_RESULT_READY_FOR_CALIBRATION_BINDING"
STATUS_HOLD: Final = "HOLD"
MAX_RECEIPT_BYTES: Final = 128 * 1024


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_once(path: Path, payload: bytes, error_name: str) -> None:
    if not path.is_absolute() or path.exists() or path.is_symlink():
        raise ValueError(error_name)
    created = False
    try:
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
                    raise OSError(f"{error_name}WriteIncomplete")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except Exception:
        if created:
            with suppress(OSError):
                path.unlink()
        raise


def export_temperature_long_window_intake_receipt(
    recording_path: str | Path, output_path: str | Path
) -> dict[str, Any]:
    """Export a public receipt only when the exact recording passes intake."""

    path = Path(output_path)
    created = False
    errors: list[str] = []
    intake = evaluate_temperature_long_window_intake(recording_path)
    try:
        if intake["status"] != INTAKE_READY:
            raise ValueError("LongWindowIntakeNotReady")
        _write_once(
            path, _canonical(intake) + b"\n", "LongWindowReceiptOutputUnavailable"
        )
        created = True
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        errors.append(str(error) or error.__class__.__name__)
        if created:
            with suppress(OSError):
                path.unlink()
    return {
        "schema": INTAKE_SCHEMA,
        "status": INTAKE_READY if created and not errors else STATUS_HOLD,
        "record_sha256": intake.get("record_sha256")
        if created and not errors
        else None,
        "labels_accepted": False,
        "private_key_accepted": False,
        "signer_invoked": False,
        "errors": errors,
    }


def build_temperature_intake_bound_detector_result(
    recording_path: str | Path,
    intake_receipt_path: str | Path,
    *,
    generated_at_utc: str,
) -> dict[str, Any]:
    """Reconstruct the receipt, replay its exact bytes, and bind both results."""

    try:
        receipt_payload = _snapshot(
            Path(intake_receipt_path), maximum=MAX_RECEIPT_BYTES
        )
    except (FileNotFoundError, OSError, ValueError) as error:
        raise ValueError("IntakeBoundDetectorReceiptUnavailable") from error
    try:
        receipt = json.loads(receipt_payload)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
        raise ValueError("IntakeBoundDetectorReceiptInvalid") from error
    if not isinstance(receipt, Mapping):
        raise ValueError("IntakeBoundDetectorReceiptInvalid")
    reconstructed = evaluate_temperature_long_window_intake(recording_path)
    if receipt != reconstructed or receipt_payload != _canonical(reconstructed) + b"\n":
        raise ValueError("IntakeBoundDetectorReceiptMismatch")
    if (
        reconstructed.get("status") != INTAKE_READY
        or reconstructed.get("eligible_for_label_blind_replay") is not True
        or reconstructed.get("labels_present") is not False
    ):
        raise ValueError("IntakeBoundDetectorIntakeNotReady")

    legacy = build_temperature_detector_result(
        recording_path, generated_at_utc=generated_at_utc
    )
    result = {
        key: value
        for key, value in legacy.items()
        if key not in {"schema", "result_sha256", "detector_contract_sha256"}
    }
    result.update(
        {
            "schema": SCHEMA,
            "long_window_intake_schema": INTAKE_SCHEMA,
            "long_window_intake_record_sha256": reconstructed["record_sha256"],
            "long_window_intake_receipt_sha256": _sha256(receipt_payload),
            "baseline_frame_count": reconstructed["baseline_frame_count"],
            "baseline_stable": reconstructed["baseline_stable"],
            "intake_reconstructed": True,
            "receipt_bound": True,
            "eligible_for_calibration_binding": True,
        }
    )
    result["detector_contract_sha256"] = _sha256(
        _canonical(
            {
                "legacy_detector_contract_sha256": legacy["detector_contract_sha256"],
                "intake_schema": INTAKE_SCHEMA,
                "result_schema": SCHEMA,
            }
        )
    )
    result["result_sha256"] = _sha256(_canonical(result))
    return result


def export_temperature_intake_bound_detector_result(
    recording_path: str | Path,
    intake_receipt_path: str | Path,
    output_path: str | Path,
    *,
    generated_at_utc: str,
) -> dict[str, Any]:
    """Atomically export one intake-bound result without labels or a signer."""

    path = Path(output_path)
    created = False
    errors: list[str] = []
    result: dict[str, Any] | None = None
    try:
        result = build_temperature_intake_bound_detector_result(
            recording_path,
            intake_receipt_path,
            generated_at_utc=generated_at_utc,
        )
        _write_once(
            path, _canonical(result) + b"\n", "IntakeBoundDetectorOutputUnavailable"
        )
        created = True
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        errors.append(str(error) or error.__class__.__name__)
        if created:
            with suppress(OSError):
                path.unlink()
    exported = result is not None and created and not errors
    return {
        "schema": SCHEMA,
        "status": STATUS_READY if exported else STATUS_HOLD,
        "result_sha256": result.get("result_sha256") if exported else None,
        "first_policy_match_index": result.get("first_policy_match_index")
        if exported
        else None,
        "intake_reconstructed": exported,
        "receipt_bound": exported,
        "eligible_for_calibration_binding": exported,
        "labels_accepted": False,
        "private_key_accepted": False,
        "signer_invoked": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "errors": errors,
    }


def pending_temperature_intake_bound_detector_result(
    long_window_intake: Mapping[str, Any],
) -> dict[str, Any]:
    ready = long_window_intake.get("status") == INTAKE_READY
    return {
        "schema": SCHEMA,
        "status": "ACTION_REQUIRED_INTAKE_BOUND_DETECTOR_RESULT"
        if ready
        else STATUS_HOLD,
        "long_window_intake_ready": ready,
        "intake_reconstructed": False,
        "receipt_bound": False,
        "eligible_for_calibration_binding": False,
        "labels_accepted": False,
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
            "export the exact governed intake receipt and replay it through the detector"
            if ready
            else "provide one accepted governed long-window intake"
        ),
        "errors": [] if ready else ["accepted governed long-window intake required"],
    }


__all__ = [
    "SCHEMA",
    "STATUS_HOLD",
    "STATUS_READY",
    "build_temperature_intake_bound_detector_result",
    "export_temperature_intake_bound_detector_result",
    "export_temperature_long_window_intake_receipt",
    "pending_temperature_intake_bound_detector_result",
]
