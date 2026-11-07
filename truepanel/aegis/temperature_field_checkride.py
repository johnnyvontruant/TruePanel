"""Read-only field checkride for the temperature coverage candidate.

The checkride consumes a returned public signing kit and privacy-sanitized
Black Box frames.  It re-runs SSHSIG verification before evaluating the
observation; a caller cannot promote a copied authentication-result mapping.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, Final

from truepanel.history.black_box import BlackBoxFrame

from .temperature_coverage import (
    CODE,
    temperature_guidance_for_snapshot,
    verify_temperature_coverage,
)
from .temperature_signing_kit import verify_temperature_signing_return

SCHEMA: Final = "truepanel.aegis-temperature-field-checkride/v1"
STATUS_BLOCKED: Final = "ACTION_REQUIRED_AUTHENTICATED_DEVELOPMENT_ACCEPTANCE"
STATUS_SIMULATION_PASSED: Final = "SIMULATION_REHEARSAL_PASSED"
STATUS_FIELD_REVIEW: Final = "FIELD_OBSERVATION_ACCEPTED_FOR_REVIEW"
STATUS_HOLD: Final = "HOLD"

_SOURCES: Final = {"holodeck-deterministic", "operator-opt-in-field"}
_FRAME_KEYS: Final = {
    "captured_at",
    "sequence",
    "telemetry",
    "lcd",
    "fan",
    "storage",
    "alerts",
    "buttons",
    "mission_control",
    "schema_version",
    "privacy",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _inventory(frame: BlackBoxFrame) -> tuple[tuple[str, int], ...]:
    devices = frame.storage.get("devices")
    if not isinstance(devices, list):
        return ()
    result: list[tuple[str, int]] = []
    for record in devices:
        if not isinstance(record, dict) or record.get("present") is not True:
            continue
        device = str(record.get("device") or "").strip()
        try:
            bay = int(record.get("physical_bay") or record.get("bay") or 0)
        except (TypeError, ValueError):
            bay = 0
        if not device or bay <= 0:
            return ()
        result.append((device, bay))
    return tuple(sorted(result))


def pending_temperature_field_checkride(
    authentication: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the live, non-invented state before a real signed return exists."""

    authenticated = (
        authentication.get("status")
        == "AUTHENTICATED_DEVELOPMENT_ACCEPTED_FOR_REVIEW"
        and authentication.get("operator_signature_verified") is True
    )
    result = {
        "schema": SCHEMA,
        "status": STATUS_HOLD if authenticated else STATUS_BLOCKED,
        "operator_signature_verified": authenticated,
        "observation_present": False,
        "observation_source": None,
        "simulation": False,
        "field_observation_reviewed": False,
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
            else "import an operator-reviewed sanitized Black Box observation"
        ),
        "errors": [] if authenticated else ["authenticated development record required"],
    }
    result["record_sha256"] = _sha256(result)
    return result


def evaluate_temperature_field_checkride(
    candidate: Mapping[str, Any],
    appraisal: Mapping[str, Any],
    confirmation: Mapping[str, Any],
    kit_directory: str,
    signature_path: str,
    verifier: Any,
    frames: Sequence[Mapping[str, Any]],
    *,
    now_utc: str,
    evidence_source: str,
    operator_opt_in: bool = False,
    incident_reviewed: bool = False,
) -> dict[str, Any]:
    """Authenticate, replay, and assess a bounded read-only observation.

    A successful deterministic result proves only that the verification path
    works.  A successful field result is accepted for separate review, never
    as production validation or candidate installation.
    """

    errors: list[str] = []
    authentication = verify_temperature_signing_return(
        dict(candidate),
        dict(appraisal),
        dict(confirmation),
        kit_directory,
        signature_path,
        verifier,
        now_utc=now_utc,
    )
    if authentication.get("status") != "AUTHENTICATED_DEVELOPMENT_ACCEPTED_FOR_REVIEW":
        errors.append("authenticated development record required")
    if evidence_source not in _SOURCES:
        errors.append("observation source is not governed")
    if evidence_source == "operator-opt-in-field":
        if operator_opt_in is not True:
            errors.append("operator opt-in is required for field evidence")
        if incident_reviewed is not True:
            errors.append("field incident outcome review is required")
    elif operator_opt_in or incident_reviewed:
        errors.append("simulation cannot claim field consent or review")

    validated: list[BlackBoxFrame] = []
    if len(frames) != 4:
        errors.append("exactly four bounded Black Box frames are required")
    else:
        for index, supplied in enumerate(frames):
            try:
                if not isinstance(supplied, Mapping) or set(supplied) != _FRAME_KEYS:
                    raise ValueError("frame has unknown or missing fields")
                frame = BlackBoxFrame.from_dict(supplied)
                if frame.as_dict() != dict(supplied):
                    raise ValueError("frame was not sanitized before admission")
                validated.append(frame)
            except (KeyError, TypeError, ValueError) as error:
                errors.append(f"frame {index}: {error}")

    fault_detected = False
    recovery_verified = False
    stable_inventory = False
    if len(validated) == 4:
        sequences = [frame.sequence for frame in validated]
        timestamps = [frame.captured_at for frame in validated]
        if any(
            right <= left
            for left, right in zip(sequences, sequences[1:], strict=False)
        ):
            errors.append("frame sequence must increase strictly")
        if any(
            right <= left
            for left, right in zip(timestamps, timestamps[1:], strict=False)
        ):
            errors.append("capture time must increase strictly")
        inventories = [_inventory(frame) for frame in validated]
        stable_inventory = bool(inventories[0]) and len(set(inventories)) == 1
        if not stable_inventory:
            errors.append("present-member identity is incomplete or unstable")

        initial_cards = temperature_guidance_for_snapshot(
            {"storage": validated[0].storage}
        )
        fault_detected = any(card.get("code") == CODE for card in initial_cards)
        if not fault_detected:
            errors.append("initial observability fault was not reproduced")

        complete = [
            not temperature_guidance_for_snapshot({"storage": frame.storage})
            for frame in validated[1:]
        ]
        verification = verify_temperature_coverage(
            {
                "code": CODE,
                "runtime": {
                    "evidence": {
                        "missing_member_count": 0 if all(complete) else 1,
                        "consecutive_complete_samples": sum(complete),
                        "identity_stable": stable_inventory,
                    }
                },
            }
        )
        recovery_verified = verification.get("status") == "passed"
        if not recovery_verified:
            errors.append("three complete identity-stable recovery observations required")

    try:
        observation_sha256 = _sha256(list(frames))
    except (TypeError, ValueError):
        observation_sha256 = None
        errors.append("observation is not canonical JSON")

    unique_errors = list(dict.fromkeys(errors))
    if unique_errors:
        status = STATUS_HOLD
    elif evidence_source == "operator-opt-in-field":
        status = STATUS_FIELD_REVIEW
    else:
        status = STATUS_SIMULATION_PASSED

    report = {
        "schema": SCHEMA,
        "status": status,
        "authentication_record_sha256": authentication.get("authentication_record_sha256"),
        "operator_signature_verified": authentication.get("operator_signature_verified")
        is True,
        "observation_source": evidence_source,
        "observation_sha256": observation_sha256,
        "frame_count": len(frames),
        "fault_detected": fault_detected,
        "stable_member_identity": stable_inventory,
        "recovery_verified": recovery_verified,
        "operator_opt_in": operator_opt_in,
        "incident_reviewed": incident_reviewed,
        "simulation": evidence_source == "holodeck-deterministic",
        "field_observation_reviewed": status == STATUS_FIELD_REVIEW,
        "eligible_for_calibration_review": status == STATUS_FIELD_REVIEW,
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
        "errors": unique_errors,
    }
    report["record_sha256"] = _sha256(report)
    return report


__all__ = [
    "STATUS_BLOCKED",
    "STATUS_FIELD_REVIEW",
    "STATUS_HOLD",
    "STATUS_SIMULATION_PASSED",
    "evaluate_temperature_field_checkride",
    "pending_temperature_field_checkride",
]
