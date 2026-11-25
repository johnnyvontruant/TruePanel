"""Unaccepted recovery-coverage candidate for missing drive temperatures.

The candidate is intentionally separate from the installed guidance catalog
and accepted v1 matrix. HoloDeck can rehearse it and Mission Control can show
its review state, but normal runtime guidance cannot emit it until a separate
acceptance step installs the candidate.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from truepanel.guidance.storage_evidence import normalize_device

CODE = "storage.temperature_telemetry_missing"
SCHEMA = "truepanel.aegis-recovery-coverage/v2-candidate"


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _smart_warning(record: Mapping[str, Any]) -> bool:
    if _text(record.get("health")).upper() == "FAILED":
        return True
    if any(
        _integer(record.get(key)) > 0
        for key in (
            "reallocated",
            "pending",
            "offline_uncorrectable",
            "reported_uncorrect",
            "media_errors",
        )
    ):
        return True
    return _text(record.get("critical_warning")).lower() not in {
        "",
        "0",
        "0x00",
        "0x0",
    }


def _step(title: str, detail: str, *, risk: str = "safe") -> dict[str, Any]:
    return {
        "title": title,
        "detail": detail,
        "risk": risk,
        "requires_shutdown": False,
        "destructive": False,
    }


def temperature_guidance_for_snapshot(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Detect a temperature blind spot only in candidate/rehearsal contexts."""

    storage = _dict(payload.get("storage"))
    members = []
    for record in _list(storage.get("devices")):
        if not isinstance(record, dict) or record.get("present") is not True:
            continue
        device = normalize_device(record.get("device") or record.get("drive"))
        if not device:
            continue
        members.append(
            {
                "pool": record.get("pool"),
                "vdev": record.get("vdev"),
                "member_id": record.get("member_id") or record.get("zfs_name"),
                "device": device,
                "bay": record.get("physical_bay") or record.get("bay"),
                "zfs_state": record.get("zfs_state") or record.get("state"),
            }
        )
    if not members:
        return []

    observed_devices: set[str] = set()
    observed_bays: set[int] = set()
    valid_readings = 0
    for reading in _list(storage.get("temperatures")):
        if not isinstance(reading, dict):
            continue
        if _number(reading.get("temperature_c", reading.get("temp"))) is None:
            continue
        valid_readings += 1
        device = normalize_device(
            reading.get("device") or reading.get("drive") or reading.get("disk")
        )
        if device:
            observed_devices.add(device)
        bay = _integer(reading.get("bay") or reading.get("physical_bay"))
        if bay > 0:
            observed_bays.add(bay)

    missing = [
        member
        for member in members
        if member["device"] not in observed_devices
        and _integer(member["bay"]) not in observed_bays
    ]
    if not missing:
        return []

    evidence = {
        "expected_member_count": len(members),
        "observed_temperature_count": valid_readings,
        "missing_member_count": len(missing),
        "missing_members": missing,
        "observed_bays": sorted(observed_bays),
        "identity_basis": "exact_device_or_explicit_physical_bay",
        "temperature_state": "unknown",
        "consecutive_complete_samples": 0,
        "identity_stable": True,
        "concurrent_smart_warning_count": sum(
            1
            for record in _list(storage.get("smart"))
            if isinstance(record, dict) and _smart_warning(record)
        ),
        "concurrent_faulted_member_count": sum(
            1
            for record in _list(storage.get("devices"))
            if isinstance(record, dict)
            and _text(record.get("zfs_state") or record.get("state")).upper()
            in {"FAULTED", "UNAVAIL", "UNAVAILABLE"}
        ),
    }
    return [
        {
            "code": CODE,
            "title": "Drive temperature telemetry is incomplete",
            "severity": "caution",
            "summary": (
                "A known present storage member has no identity-matched "
                "temperature observation. Its thermal state is unknown."
            ),
            "evidence_fields": list(evidence),
            "immediate_actions": [
                _step(
                    "Verify the read-only member identity",
                    "Verify the read-only member identity and restore its temperature collector path.",
                )
            ],
            "diagnosis": [
                _step(
                    "Reconcile inventory and temperature identities",
                    "Compare exact device and explicit physical-bay identities; do not infer a bay from list order.",
                )
            ],
            "remediation": [
                _step(
                    "Restore the narrowest collector path",
                    "Repair only the missing read-only telemetry or mapping path after identity is confirmed.",
                    risk="caution",
                )
            ],
            "verification": [
                _step(
                    "Require sustained complete observations",
                    "Require every expected member to report an identity-matched temperature for three consecutive observations.",
                )
            ],
            "escalation": (
                "Escalate if the member identity is unstable, SMART/ZFS evidence worsens, "
                "or the collector cannot be restored without privileged changes."
            ),
            "model_specific": False,
            "sources": [],
            "runtime": {
                "active": True,
                "phase": "diagnose",
                "evidence": evidence,
                "action_gate": {
                    "safe_checks": True,
                    "physical_service_ready": False,
                    "destructive_actions_ready": False,
                    "blocked_by": [
                        "temperature_state_unknown",
                        "three_complete_observations_required",
                    ],
                },
            },
        }
    ]


def verify_temperature_coverage(card: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate the candidate without changing the accepted verifier module."""

    evidence = _dict(_dict(card.get("runtime")).get("evidence"))
    missing = _integer(evidence.get("missing_member_count"))
    complete_samples = _integer(evidence.get("consecutive_complete_samples"))
    passed = (
        missing == 0
        and complete_samples >= 3
        and evidence.get("identity_stable") is True
    )
    return {
        "strategy": "drive_temperature_inventory_recheck",
        "automated": True,
        "status": "passed" if passed else "pending",
        "criteria": (
            "Every expected present member has an exact identity-matched "
            "temperature for at least three consecutive observations."
        ),
    }


def rehearse_temperature_coverage() -> dict[str, Any]:
    """Exercise the candidate verifier without installing the candidate."""

    before = verify_temperature_coverage(
        {
            "code": CODE,
            "runtime": {
                "phase": "verify",
                "evidence": {
                    "missing_member_count": 1,
                    "consecutive_complete_samples": 0,
                    "identity_stable": True,
                },
            },
        }
    )
    after = verify_temperature_coverage(
        {
            "code": CODE,
            "runtime": {
                "phase": "verify",
                "evidence": {
                    "missing_member_count": 0,
                    "consecutive_complete_samples": 3,
                    "identity_stable": True,
                },
            },
        }
    )
    evidence = {
        "code": CODE,
        "simulation": True,
        "production_mutation": False,
        "verification_strategy": after.get("strategy"),
        "fault_present_result": before.get("status"),
        "recovered_result": after.get("status"),
    }
    digest = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    passed = before.get("status") == "pending" and after.get("status") == "passed"
    return {
        **evidence,
        "status": "passed" if passed else "failed",
        "evidence_sha256": digest,
    }


def _sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_temperature_coverage_candidate(
    accepted_matrix: Mapping[str, Any],
    rehearsal: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the reviewable 9/9 candidate while preserving accepted 8/8."""

    rehearsal = dict(rehearsal or rehearse_temperature_coverage())
    verifier = verify_temperature_coverage({"code": CODE, "runtime": {"evidence": {}}})
    entry = {
        "code": CODE,
        "title": "Drive temperature telemetry is incomplete",
        "severity": "caution",
        "detector": "Exact present-member and finite-temperature reconciliation",
        "regression_scenarios": ("aegis-drive-temperature-blind-spot",),
        "recovery_owner": "Pathfinder + Lifeline",
        "diagnosis_owner": "Operator Guidance",
        "diagnostic_evidence": [
            "expected_member_count",
            "observed_temperature_count",
            "missing_members",
            "identity_basis",
            "temperature_state",
        ],
        "actionable_guidance": True,
        "verification": {
            "strategy": verifier.get("strategy"),
            "machine_verifiable": verifier.get("automated") is True,
            "criteria": verifier.get("criteria"),
        },
        "rehearsal": rehearsal,
        "coverage_state": "TRUSTED" if rehearsal.get("status") == "passed" else "GAP",
        "gaps": [] if rehearsal.get("status") == "passed" else ["candidate rehearsal failed"],
    }
    entries = deepcopy(list(accepted_matrix.get("entries", []))) + [entry]
    trusted = sum(item.get("coverage_state") == "TRUSTED" for item in entries)
    candidate = {
        "schema": SCHEMA,
        "schema_version": 2,
        "read_only": True,
        "accepted": False,
        "installed": False,
        "automatic_acceptance": False,
        "review_required": True,
        "status": "READY_FOR_OPERATOR_REVIEW" if trusted == len(entries) else "HOLD",
        "predecessor_sha256": _sha256(dict(accepted_matrix)),
        "contract": "actionable alerts require guidance, verification, and simulation",
        "total": len(entries),
        "trusted": trusted,
        "gaps": len(entries) - trusted,
        "entries": entries,
    }
    candidate["candidate_sha256"] = _sha256(candidate)
    return candidate


def validate_temperature_coverage_candidate(candidate: Mapping[str, Any]) -> tuple[str, ...]:
    """Return fail-closed candidate contract violations."""

    errors = []
    if candidate.get("schema") != SCHEMA:
        errors.append("unexpected candidate schema")
    if candidate.get("accepted") is not False or candidate.get("installed") is not False:
        errors.append("candidate must remain unaccepted and uninstalled")
    if candidate.get("automatic_acceptance") is not False:
        errors.append("candidate must forbid automatic acceptance")
    if candidate.get("total") != 9 or candidate.get("trusted") != 9 or candidate.get("gaps") != 0:
        errors.append("candidate must contain nine rehearsed paths with no gaps")
    entries = [item for item in candidate.get("entries", []) if isinstance(item, dict)]
    matching = [item for item in entries if item.get("code") == CODE]
    if len(matching) != 1 or matching[0].get("coverage_state") != "TRUSTED":
        errors.append("temperature coverage row is missing or untrusted")
    elif matching[0].get("rehearsal", {}).get("status") != "passed":
        errors.append("temperature coverage rehearsal did not pass")
    return tuple(errors)


__all__ = [
    "CODE",
    "SCHEMA",
    "build_temperature_coverage_candidate",
    "rehearse_temperature_coverage",
    "temperature_guidance_for_snapshot",
    "validate_temperature_coverage_candidate",
    "verify_temperature_coverage",
]
