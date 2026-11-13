"""Independent label-blind passive replay of one confirmed recording."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from statistics import fmean
from typing import Any, Final

from .temperature_calibration_candidate_appraisal import _canonical
from .temperature_confirmed_recording_intake import (
    BASELINE_SAMPLE_COUNT,
    verify_recorded_temperature_confirmed_recording_intake,
)

SCHEMA: Final = "truepanel.aegis-temperature-label-blind-passive-replay/v1"
RECEIPT_SCHEMA: Final = (
    "truepanel.aegis-temperature-label-blind-passive-replay-receipt/v1"
)
DETECTOR_ID: Final = "aegis-independent-shared-cooling-replay-v1"
STATUS_READY: Final = "REPLAY_EVIDENCE_PRESERVED_FOR_MANUAL_REVIEW"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_CONFIRMED_RECORDING_INTAKE"
STATUS_HOLD: Final = "HOLD"

_DENIED = (
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
_RECEIPT_KEYS = {
    "schema",
    "status",
    "replayed_at_utc",
    "intake_receipt_sha256",
    "recording_sha256",
    "detector_id",
    "detector_contract_sha256",
    "label_blind",
    "labels_present",
    "sample_count",
    "baseline_sample_count",
    "probable_root_cause",
    "confidence",
    "supporting_evidence",
    "first_shared_cooling_match_sample",
    "first_isolated_threshold_sample",
    "lead_samples",
    "coverage_total",
    "coverage_trusted",
    "coverage_gaps",
    "passive_replay_performed",
    "live_capture_performed",
    "receipt_sha256",
    *_DENIED,
}


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        value if isinstance(value, bytes) else _canonical(value)
    ).hexdigest()


def detector_contract() -> dict[str, Any]:
    """Return the fixed, replaceable detector contract used by this replay."""
    return {
        "schema": "truepanel.aegis-shared-cooling-replay-contract/v1",
        "detector_id": DETECTOR_ID,
        "baseline_samples": BASELINE_SAMPLE_COUNT,
        "required_evidence": {
            "fan_rpm_loss_ratio": 0.06,
            "fan_speed_ratio_loss": 0.05,
            "cpu_temperature_rise_c": 1.25,
            "system_temperature_rise_c": 1.0,
            "physical_disk_temperature_rise_c": 0.85,
        },
        "isolated_thresholds": {
            "cpu_temperature_rise_c": 5.5,
            "system_temperature_rise_c": 4.5,
            "physical_disk_temperature_rise_c": 3.8,
        },
        "confidence": {
            "base": 0.45,
            "fan_rpm": 0.14,
            "fan_speed_ratio": 0.12,
            "cpu_temperature": 0.06,
            "system_temperature": 0.08,
            "physical_disk_temperature": 0.10,
            "cap": 0.95,
        },
        "labels_allowed": False,
        "online_learning": False,
        "threshold_tuning": False,
    }


def _replay(recording: Mapping[str, Any]) -> dict[str, Any]:
    samples = recording["samples"]
    baseline = samples[:BASELINE_SAMPLE_COUNT]
    means = {
        key: fmean(float(item[key]) for item in baseline)
        for key in (
            "fan_speed_rpm",
            "fan_speed_ratio",
            "cpu_temperature_c",
            "system_temperature_c",
            "physical_disk_temperature_c",
        )
    }
    contract = detector_contract()
    limits = contract["required_evidence"]
    isolated = contract["isolated_thresholds"]
    first_match = None
    first_isolated = None
    evidence: list[dict[str, Any]] = []
    for sample in samples[BASELINE_SAMPLE_COUNT:]:
        index = int(sample["sequence"])
        changes = {
            "fan_rpm_loss_ratio": round(
                (means["fan_speed_rpm"] - float(sample["fan_speed_rpm"]))
                / means["fan_speed_rpm"],
                6,
            ),
            "fan_speed_ratio_loss": round(
                means["fan_speed_ratio"] - float(sample["fan_speed_ratio"]), 6
            ),
            "cpu_temperature_rise_c": round(
                float(sample["cpu_temperature_c"]) - means["cpu_temperature_c"],
                6,
            ),
            "system_temperature_rise_c": round(
                float(sample["system_temperature_c"]) - means["system_temperature_c"],
                6,
            ),
            "physical_disk_temperature_rise_c": round(
                float(sample["physical_disk_temperature_c"])
                - means["physical_disk_temperature_c"],
                6,
            ),
        }
        if first_match is None and all(
            changes[key] >= float(value) for key, value in limits.items()
        ):
            first_match = index
            evidence = [
                {"signal": key, "observed": changes[key], "required": value}
                for key, value in limits.items()
            ]
        if first_isolated is None and any(
            changes[key] >= float(value) for key, value in isolated.items()
        ):
            first_isolated = index
    weights = contract["confidence"]
    confidence = (
        min(
            float(weights["cap"]),
            float(weights["base"])
            + sum(float(weights[key]) for key in weights if key not in {"base", "cap"}),
        )
        if first_match is not None
        else 0.0
    )
    return {
        "probable_root_cause": (
            "Shared chassis cooling degradation" if first_match is not None else None
        ),
        "confidence": round(confidence, 2),
        "supporting_evidence": evidence,
        "first_shared_cooling_match_sample": first_match,
        "first_isolated_threshold_sample": first_isolated,
        "lead_samples": (
            first_isolated - first_match
            if first_match is not None and first_isolated is not None
            else None
        ),
    }


def _commit(registry: Path, digest: str, receipt: Mapping[str, Any]) -> str:
    if not registry.is_absolute() or registry.is_symlink():
        raise ValueError("LabelBlindReplayRegistryUnavailable")
    info = registry.stat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("LabelBlindReplayRegistryUnsafe")
    destination = registry / f"{digest}.json"
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    try:
        payload = _canonical(receipt) + b"\n"
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("LabelBlindReplayWriteIncomplete")
            view = view[written:]
        os.fsync(descriptor)
    except BaseException:
        with suppress(OSError):
            destination.unlink()
        raise
    finally:
        os.close(descriptor)
    return destination.name


def evaluate_temperature_label_blind_passive_replay(
    plan_path: str | Path,
    verifier: Any,
    confirmation_statement_path: str | Path,
    confirmation_signature_path: str | Path,
    confirmation_receipt_path: str | Path,
    recording_path: str | Path,
    intake_receipt_path: str | Path,
    registry_path: str | Path,
    *,
    now_utc: str,
) -> dict[str, Any]:
    """Replay admitted evidence once, without labels or operational authority."""
    errors: list[str] = []
    receipt: dict[str, Any] = {}
    filename = None
    try:
        intake, recording = verify_recorded_temperature_confirmed_recording_intake(
            plan_path,
            verifier,
            confirmation_statement_path,
            confirmation_signature_path,
            confirmation_receipt_path,
            recording_path,
            intake_receipt_path,
            now_utc=now_utc,
        )
        replay = _replay(recording)
        if (
            replay["probable_root_cause"] is None
            or replay["first_shared_cooling_match_sample"] is None
            or replay["first_isolated_threshold_sample"] is None
        ):
            raise ValueError("LabelBlindReplaySharedCoolingEvidenceInsufficient")
        contract = detector_contract()
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": STATUS_READY,
            "replayed_at_utc": now_utc,
            "intake_receipt_sha256": intake["receipt_sha256"],
            "recording_sha256": intake["recording_sha256"],
            "detector_id": DETECTOR_ID,
            "detector_contract_sha256": _sha256(contract),
            "label_blind": True,
            "labels_present": False,
            "sample_count": intake["sample_count"],
            "baseline_sample_count": intake["baseline_sample_count"],
            **replay,
            "coverage_total": 8,
            "coverage_trusted": 8,
            "coverage_gaps": 0,
            "passive_replay_performed": True,
            "live_capture_performed": False,
            **{key: False for key in sorted(_DENIED)},
        }
        receipt["receipt_sha256"] = _sha256(receipt)
        if set(receipt) != _RECEIPT_KEYS:
            raise ValueError("LabelBlindReplayReceiptFieldsInvalid")
        filename = _commit(Path(registry_path), intake["receipt_sha256"], receipt)
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
    ready = filename is not None and not errors
    return {
        "schema": SCHEMA,
        "status": STATUS_READY if ready else STATUS_HOLD,
        "replay_receipt_written": ready,
        "receipt_filename": filename,
        "receipt_sha256": receipt.get("receipt_sha256") if ready else None,
        "label_blind": ready,
        "labels_present": False,
        "probable_root_cause": receipt.get("probable_root_cause") if ready else None,
        "confidence": receipt.get("confidence") if ready else None,
        "supporting_evidence": receipt.get("supporting_evidence", []) if ready else [],
        "first_shared_cooling_match_sample": receipt.get(
            "first_shared_cooling_match_sample"
        )
        if ready
        else None,
        "first_isolated_threshold_sample": receipt.get(
            "first_isolated_threshold_sample"
        )
        if ready
        else None,
        "lead_samples": receipt.get("lead_samples") if ready else None,
        "coverage_total": 8,
        "coverage_trusted": 8,
        "coverage_gaps": 0,
        "passive_replay_performed": ready,
        "live_capture_performed": False,
        **{key: False for key in _DENIED},
        "errors": errors,
    }


def pending_temperature_label_blind_passive_replay(
    intake: Mapping[str, Any],
) -> dict[str, Any]:
    admitted = intake.get("recording_admitted") is True
    return {
        "schema": SCHEMA,
        "status": STATUS_REQUIRED if admitted else STATUS_HOLD,
        "replay_receipt_written": False,
        "label_blind": False,
        "labels_present": False,
        "probable_root_cause": None,
        "confidence": None,
        "supporting_evidence": [],
        "first_shared_cooling_match_sample": None,
        "first_isolated_threshold_sample": None,
        "lead_samples": None,
        "coverage_total": 8,
        "coverage_trusted": 8,
        "coverage_gaps": 0,
        "passive_replay_performed": False,
        "live_capture_performed": False,
        **{key: False for key in _DENIED},
        "next_action": (
            "Admit one exact confirmed sanitized recording first."
            if not admitted
            else "Replay the exact intake once without labels and preserve its digest-bound evidence receipt."
        ),
    }


__all__ = [
    "DETECTOR_ID",
    "SCHEMA",
    "STATUS_HOLD",
    "STATUS_READY",
    "detector_contract",
    "evaluate_temperature_label_blind_passive_replay",
    "pending_temperature_label_blind_passive_replay",
]
