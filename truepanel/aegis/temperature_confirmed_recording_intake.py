"""Content-bound intake for one confirmed, operator-supplied recording."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from .temperature_calibration_candidate_appraisal import (
    MAX_PUBLIC_BYTES,
    _canonical,
    _snapshot,
)
from .temperature_field_checkride_confirmation import (
    DECISION_CONFIRM,
    verify_recorded_temperature_field_checkride_confirmation,
)

SCHEMA: Final = "truepanel.aegis-temperature-confirmed-recording-intake/v1"
RECORDING_SCHEMA: Final = "truepanel.black-box-temperature-field-recording/v1"
RECEIPT_SCHEMA: Final = (
    "truepanel.aegis-temperature-confirmed-recording-intake-receipt/v1"
)
STATUS_READY: Final = "READY_FOR_LABEL_BLIND_PASSIVE_REPLAY"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_OPERATOR_SUPPLIED_SANITIZED_RECORDING"
STATUS_HOLD: Final = "HOLD"
EXPECTED_SAMPLE_COUNT: Final = 48
BASELINE_SAMPLE_COUNT: Final = 12

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
_RECORDING_KEYS = {"schema", "manifest", "samples"}
_MANIFEST_KEYS = {
    "source",
    "custody",
    "classification",
    "system_profile",
    "workload_profile",
    "signals",
    "labels_present",
    "captured_by_truepanel",
}
_SAMPLE_KEYS = {
    "sequence",
    "timestamp",
    "fan_speed_rpm",
    "fan_speed_ratio",
    "cpu_temperature_c",
    "system_temperature_c",
    "physical_disk_temperature_c",
}
_RECEIPT_KEYS = {
    "schema",
    "status",
    "recorded_at_utc",
    "confirmation_receipt_sha256",
    "plan_sha256",
    "recording_sha256",
    "recording_bytes",
    "sample_count",
    "baseline_sample_count",
    "system_profile",
    "workload_profile",
    "signals",
    "privacy_verified",
    "custody_verified",
    "sequence_verified",
    "stable_baseline_verified",
    "recording_present",
    "capture_performed",
    "receipt_sha256",
    *_DENIED,
}
_PROFILE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_FORBIDDEN = {
    "credential",
    "hostname",
    "network-address",
    "ip-address",
    "serial",
    "wwid",
    "wwn",
    "pool-content",
    "file-path",
    "mac-address",
    "username",
    "password",
    "token",
    "secret",
}


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        value if isinstance(value, bytes) else _canonical(value)
    ).hexdigest()


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("ConfirmedRecordingTimestampInvalid")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC:
        raise ValueError("ConfirmedRecordingTimestampInvalid")
    return parsed


def _expected_signals() -> list[dict[str, Any]]:
    return [
        {"name": "hw.fan.speed", "unit": "rpm", "required": True},
        {"name": "hw.fan.speed_ratio", "unit": "1", "required": True},
        {"name": "hw.temperature.cpu", "unit": "Cel", "required": True},
        {"name": "hw.temperature.system", "unit": "Cel", "required": True},
        {"name": "hw.temperature.physical_disk", "unit": "Cel", "required": True},
        {"name": "sample.sequence", "unit": "1", "required": True},
        {"name": "sample.timestamp", "unit": "UTC", "required": True},
    ]


def _privacy_walk(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower().replace("_", "-")
            if any(term in normalized for term in _FORBIDDEN):
                raise ValueError("ConfirmedRecordingPrivacyFieldForbidden")
            _privacy_walk(child)
    elif isinstance(value, list):
        for child in value:
            _privacy_walk(child)
    elif isinstance(value, str):
        normalized = value.lower().replace("_", "-")
        if any(term in normalized for term in _FORBIDDEN):
            raise ValueError("ConfirmedRecordingPrivacyValueForbidden")


def _recording(path: Path) -> tuple[bytes, dict[str, Any]]:
    payload = _snapshot(path, MAX_PUBLIC_BYTES)
    value = json.loads(payload)
    if (
        not isinstance(value, dict)
        or set(value) != _RECORDING_KEYS
        or payload != _canonical(value) + b"\n"
    ):
        raise ValueError("ConfirmedRecordingCanonicalFormInvalid")
    manifest = value["manifest"]
    samples = value["samples"]
    if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_KEYS:
        raise ValueError("ConfirmedRecordingManifestInvalid")
    if manifest != {
        "source": "operator-supplied-sanitized-black-box",
        "custody": "operator-supplied-after-separate-confirmation",
        "classification": "sanitized",
        "system_profile": manifest.get("system_profile"),
        "workload_profile": manifest.get("workload_profile"),
        "signals": _expected_signals(),
        "labels_present": False,
        "captured_by_truepanel": False,
    }:
        raise ValueError("ConfirmedRecordingCustodyContractMismatch")
    if not all(
        _PROFILE.fullmatch(str(manifest[key]))
        for key in ("system_profile", "workload_profile")
    ):
        raise ValueError("ConfirmedRecordingProfileInvalid")
    if not isinstance(samples, list) or len(samples) != EXPECTED_SAMPLE_COUNT:
        raise ValueError("ConfirmedRecordingSampleCountInvalid")
    previous: datetime | None = None
    for index, sample in enumerate(samples):
        if (
            not isinstance(sample, dict)
            or set(sample) != _SAMPLE_KEYS
            or sample["sequence"] != index
        ):
            raise ValueError("ConfirmedRecordingSampleInvalid")
        current = _timestamp(sample["timestamp"])
        if previous is not None and current <= previous:
            raise ValueError("ConfirmedRecordingSequenceNotMonotonic")
        previous = current
        numeric = [sample[key] for key in _SAMPLE_KEYS - {"sequence", "timestamp"}]
        if any(
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(item)
            for item in numeric
        ):
            raise ValueError("ConfirmedRecordingSignalInvalid")
        if not (0 <= sample["fan_speed_ratio"] <= 1 and sample["fan_speed_rpm"] >= 0):
            raise ValueError("ConfirmedRecordingSignalRangeInvalid")
    baseline = samples[:BASELINE_SAMPLE_COUNT]
    limits = {
        "fan_speed_rpm": 25.0,
        "fan_speed_ratio": 0.02,
        "cpu_temperature_c": 0.6,
        "system_temperature_c": 0.6,
        "physical_disk_temperature_c": 0.6,
    }
    for key, limit in limits.items():
        values = [float(sample[key]) for sample in baseline]
        if max(values) - min(values) > limit:
            raise ValueError("ConfirmedRecordingBaselineUnstable")
    _privacy_walk(value)
    return payload, value


def _commit(registry: Path, digest: str, receipt: Mapping[str, Any]) -> str:
    if not registry.is_absolute() or registry.is_symlink():
        raise ValueError("ConfirmedRecordingIntakeRegistryUnavailable")
    info = registry.stat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("ConfirmedRecordingIntakeRegistryUnsafe")
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


def evaluate_temperature_confirmed_recording_intake(
    plan_path: str | Path,
    verifier: Any,
    confirmation_statement_path: str | Path,
    confirmation_signature_path: str | Path,
    confirmation_receipt_path: str | Path,
    recording_path: str | Path,
    registry_path: str | Path,
    *,
    now_utc: str,
) -> dict[str, Any]:
    """Admit one immutable recording for later passive replay; never capture it."""
    errors: list[str] = []
    receipt: dict[str, Any] = {}
    filename: str | None = None
    admitted = False
    try:
        confirmation = verify_recorded_temperature_field_checkride_confirmation(
            plan_path,
            verifier,
            confirmation_statement_path,
            confirmation_signature_path,
            confirmation_receipt_path,
            now_utc=now_utc,
        )
        if (
            confirmation["decision"] != DECISION_CONFIRM
            or confirmation["operator_supplied_recording_review_eligible"] is not True
        ):
            raise ValueError("ConfirmedRecordingIntakeNotConfirmed")
        payload, recording = _recording(Path(recording_path))
        manifest = recording["manifest"]
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": STATUS_READY,
            "recorded_at_utc": now_utc,
            "confirmation_receipt_sha256": confirmation["receipt_sha256"],
            "plan_sha256": confirmation["plan_sha256"],
            "recording_sha256": _sha256(payload),
            "recording_bytes": len(payload),
            "sample_count": len(recording["samples"]),
            "baseline_sample_count": BASELINE_SAMPLE_COUNT,
            "system_profile": manifest["system_profile"],
            "workload_profile": manifest["workload_profile"],
            "signals": manifest["signals"],
            "privacy_verified": True,
            "custody_verified": True,
            "sequence_verified": True,
            "stable_baseline_verified": True,
            "recording_present": True,
            "capture_performed": False,
            **{key: False for key in sorted(_DENIED)},
        }
        receipt["receipt_sha256"] = _sha256(receipt)
        if set(receipt) != _RECEIPT_KEYS:
            raise ValueError("ConfirmedRecordingIntakeReceiptFieldsInvalid")
        filename = _commit(Path(registry_path), confirmation["receipt_sha256"], receipt)
        admitted = True
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        KeyError,
        OSError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as error:
        errors.append(
            (str(error) or error.__class__.__name__)
            if isinstance(error, ValueError)
            else error.__class__.__name__
        )
    return {
        "schema": SCHEMA,
        "status": STATUS_READY if admitted else STATUS_HOLD,
        "recording_admitted": admitted,
        "receipt_filename": filename,
        "receipt_sha256": receipt.get("receipt_sha256") if admitted else None,
        "confirmation_present": admitted,
        "recording_present": admitted,
        "recording_sha256": receipt.get("recording_sha256") if admitted else None,
        "sample_count": receipt.get("sample_count", 0),
        "privacy_verified": admitted,
        "custody_verified": admitted,
        "sequence_verified": admitted,
        "stable_baseline_verified": admitted,
        "capture_performed": False,
        **{key: False for key in _DENIED},
        "errors": errors,
    }


def pending_temperature_confirmed_recording_intake(
    confirmation: Mapping[str, Any],
) -> dict[str, Any]:
    confirmed = confirmation.get("operator_supplied_recording_review_eligible") is True
    return {
        "schema": SCHEMA,
        "status": STATUS_REQUIRED if confirmed else STATUS_HOLD,
        "confirmation_present": confirmed,
        "recording_present": False,
        "recording_admitted": False,
        "sample_count": 0,
        "privacy_verified": False,
        "custody_verified": False,
        "sequence_verified": False,
        "stable_baseline_verified": False,
        "capture_performed": False,
        **{key: False for key in _DENIED},
        "next_action": "Provide one protected canonical sanitized recording from the operator; TruePanel will verify and digest it without capture or replay.",
    }


__all__ = [
    "BASELINE_SAMPLE_COUNT",
    "EXPECTED_SAMPLE_COUNT",
    "RECORDING_SCHEMA",
    "SCHEMA",
    "STATUS_HOLD",
    "STATUS_READY",
    "evaluate_temperature_confirmed_recording_intake",
    "pending_temperature_confirmed_recording_intake",
]
