"""Content-bound, passive-only plan for a temperature field checkride."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from .temperature_calibration_candidate_appraisal import (
    DECISION_APPROVE,
    MAX_PUBLIC_BYTES,
    _canonical,
    _snapshot,
    verify_recorded_temperature_calibration_candidate_appraisal,
)

SCHEMA: Final = "truepanel.aegis-temperature-field-checkride-plan/v1"
STATUS_READY: Final = "READY_FOR_SEPARATE_FIELD_CHECKRIDE_CONFIRMATION"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_FIELD_CHECKRIDE_PLAN"
STATUS_HOLD: Final = "HOLD"

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


def expected_temperature_field_checkride_contract() -> dict[str, Any]:
    """Return the one reviewed test-card contract accepted by the builder."""
    return {
        "schema": "truepanel.aegis-temperature-field-checkride-contract/v1",
        "mode": "operator-supplied-recording-passive-replay-only",
        "source": {
            "kind": "sanitized-black-box-recording",
            "custody": "operator-supplied-after-separate-confirmation",
            "live_host_path_allowed": False,
            "truepanel_capture_allowed": False,
        },
        "preflight": [
            "separate operator confirmation is recorded for this exact plan digest",
            "recording is canonical, owner-protected, size-bounded, and content-addressed",
            "timestamps and sequences increase monotonically",
            "at least twelve stable baseline samples precede the observation window",
            "workload and system-profile identifiers are pseudonymous and fixed",
        ],
        "passive_observations": [
            {"name": "hw.fan.speed", "unit": "rpm", "required": True},
            {"name": "hw.fan.speed_ratio", "unit": "1", "required": True},
            {"name": "hw.temperature.cpu", "unit": "Cel", "required": True},
            {"name": "hw.temperature.system", "unit": "Cel", "required": True},
            {
                "name": "hw.temperature.physical_disk",
                "unit": "Cel",
                "required": True,
            },
            {"name": "sample.sequence", "unit": "1", "required": True},
            {"name": "sample.timestamp", "unit": "UTC", "required": True},
        ],
        "privacy": {
            "classification": "sanitized",
            "allowed_identity": [
                "pseudonymous-system-profile",
                "pseudonymous-workload-profile",
                "logical-sensor-role",
            ],
            "forbidden": [
                "credentials",
                "hostnames",
                "network-addresses",
                "serial-numbers",
                "wwids",
                "wwns",
                "pool-contents",
                "file-paths",
            ],
        },
        "abort_criteria": [
            "recording identity, schema, digest, or custody changes",
            "a required signal is missing, stale, non-finite, or discontinuous",
            "a hard thermal or fan alert is present",
            "baseline, workload, system profile, or sensor identity drifts",
            "privacy review finds a forbidden field or unredacted identifier",
            "any step requests live-host access, capture, configuration, service, storage, network, or hardware authority",
        ],
        "required_verification_evidence": [
            "authenticated appraisal statement, signature, and receipt digests",
            "exact candidate dossier digest and seven evidence subjects",
            "exact recording digest and sanitized manifest",
            "label-blind detector result and first-match evidence",
            "isolated-threshold comparison and lead-time measurement",
            "Recovery Coverage Matrix digest with 8/8 trusted and zero gaps",
            "HoloDeck replay digest and abort outcome",
        ],
        "success_criteria": [
            "shared-cooling hypothesis is evidence-backed with explicit confidence",
            "detector lead is measured against isolated thresholds",
            "all abort criteria remain clear",
            "result is preserved for independent review without promotion",
        ],
        "separate_confirmation_required": True,
        **{key: False for key in _DENIED},
    }


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical(value)
    return hashlib.sha256(payload).hexdigest()


def assemble_temperature_field_checkride_plan(
    dossier_path: str | Path,
    verifier: Any,
    appraisal_statement_path: str | Path,
    appraisal_signature_path: str | Path,
    appraisal_receipt_path: str | Path,
    contract: Mapping[str, Any],
    output_path: str | Path,
    *,
    now_utc: str,
) -> dict[str, Any]:
    """Build one immutable plan; never collect evidence or authorize execution."""
    errors: list[str] = []
    plan: dict[str, Any] = {}
    created = False
    try:
        appraisal = verify_recorded_temperature_calibration_candidate_appraisal(
            dossier_path,
            verifier,
            appraisal_statement_path,
            appraisal_signature_path,
            appraisal_receipt_path,
            now_utc=now_utc,
        )
        if (
            appraisal["decision"] != DECISION_APPROVE
            or appraisal["manual_field_checkride_planning_eligible"] is not True
        ):
            raise ValueError("FieldCheckridePlanAppraisalNotApproved")
        supplied_contract = dict(contract)
        if supplied_contract != expected_temperature_field_checkride_contract():
            raise ValueError("FieldCheckridePlanContractMismatch")
        dossier_bytes = _snapshot(Path(dossier_path), MAX_PUBLIC_BYTES)
        dossier = json.loads(dossier_bytes)
        plan = {
            "schema": SCHEMA,
            "status": STATUS_READY,
            "assembled_at_utc": now_utc,
            "appraisal_receipt_sha256": appraisal["receipt_sha256"],
            "dossier_sha256": appraisal["dossier_sha256"],
            "dossier_subjects": appraisal["dossier_subjects"],
            "contract": supplied_contract,
            "coverage": {"total": 8, "trusted": 8, "gaps": 0},
            "proof_target": {
                "shared_cooling_first_match_sample": 19,
                "isolated_threshold_first_match_sample": 46,
                "lead_samples": 27,
            },
            "separate_confirmation_required": True,
            "confirmation_present": False,
            "recording_present": False,
            "verification_evidence_present": False,
            **{key: False for key in _DENIED},
        }
        if dossier.get("dossier_sha256") != plan["dossier_sha256"]:
            raise ValueError("FieldCheckridePlanDossierMismatch")
        plan["plan_sha256"] = _sha256(plan)
        destination = Path(output_path)
        if not destination.is_absolute() or destination.exists():
            raise ValueError("FieldCheckridePlanOutputUnavailable")
        descriptor = os.open(
            destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600
        )
        try:
            payload = _canonical(plan) + b"\n"
            written = 0
            while written < len(payload):
                written += os.write(descriptor, payload[written:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        created = True
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        KeyError,
        OSError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as error:
        errors.append(str(error) or error.__class__.__name__)
    return {
        "schema": SCHEMA,
        "status": STATUS_READY if created else STATUS_HOLD,
        "plan_created": created,
        "plan_sha256": plan.get("plan_sha256") if created else None,
        "separate_confirmation_required": True,
        "confirmation_present": False,
        "recording_present": False,
        "verification_evidence_present": False,
        **{key: False for key in _DENIED},
        "errors": errors,
    }


def pending_temperature_field_checkride_plan(
    appraisal: Mapping[str, Any],
) -> dict[str, Any]:
    planning_eligible = (
        appraisal.get("manual_field_checkride_planning_eligible") is True
    )
    return {
        "schema": SCHEMA,
        "status": STATUS_REQUIRED if planning_eligible else STATUS_HOLD,
        "authenticated_appraisal_present": planning_eligible,
        "plan_ready": False,
        "separate_confirmation_required": True,
        "confirmation_present": False,
        "recording_present": False,
        "verification_evidence_present": False,
        **{key: False for key in _DENIED},
        "next_action": "Review one content-bound passive test card, then confirm it separately before any operator-supplied recording exists.",
    }


__all__ = [
    "SCHEMA",
    "STATUS_HOLD",
    "STATUS_READY",
    "assemble_temperature_field_checkride_plan",
    "expected_temperature_field_checkride_contract",
    "pending_temperature_field_checkride_plan",
]
