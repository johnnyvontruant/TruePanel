"""Read-only what-if simulation for Project ORACLE Ghost Mode."""

from __future__ import annotations

from typing import Any


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def simulate_drive_failure(
    storage: dict[str, Any],
    *,
    bay: int | None = None,
    device: str | None = None,
) -> dict[str, Any]:
    """Project the read-only consequences of one drive becoming unavailable.

    Ghost Mode never calls a storage API and never changes the supplied
    snapshot.  It only reasons from already-published topology/redundancy
    evidence.  Ambiguous identity fails closed instead of guessing.
    """

    if bay is None and not device:
        raise ValueError("Ghost Mode requires a physical bay or device identity")

    candidates = []
    for record in _safe_list(storage.get("devices")):
        if not isinstance(record, dict) or record.get("present") is False:
            continue
        matches_bay = bay is not None and _int_or_none(record.get("physical_bay")) == bay
        matches_device = bool(device) and str(record.get("device") or "") == str(device)
        if matches_bay or matches_device:
            candidates.append(record)

    if len(candidates) != 1:
        return {
            "schema_version": 1,
            "simulation": True,
            "read_only": True,
            "production_mutation": False,
            "available": False,
            "reason": "drive_identity_ambiguous_or_unresolved",
            "destructive_actions": False,
        }

    target = dict(candidates[0])
    pool_name = str(target.get("pool") or "").strip()
    if not pool_name:
        return {
            "schema_version": 1,
            "simulation": True,
            "read_only": True,
            "production_mutation": False,
            "available": False,
            "reason": "target_not_correlated_to_pool",
            "destructive_actions": False,
        }

    pool = next(
        (
            record
            for record in _safe_list(storage.get("pools"))
            if isinstance(record, dict)
            and str(record.get("name") or "").strip() == pool_name
        ),
        {},
    )
    current_state = str(
        _safe_dict(pool).get("health")
        or _safe_dict(pool).get("state")
        or "UNKNOWN"
    ).strip().upper()

    redundancy = _int_or_none(target.get("remaining_redundancy"))
    if redundancy is None:
        return {
            "schema_version": 1,
            "simulation": True,
            "read_only": True,
            "production_mutation": False,
            "available": False,
            "reason": "redundancy_not_verified",
            "destructive_actions": False,
            "target": {
                "physical_bay": target.get("physical_bay"),
                "pool": pool_name,
            },
        }

    if current_state == "ONLINE" and redundancy >= 1:
        projected_state = "DEGRADED"
        data_availability = "AVAILABLE"
    elif current_state in {"DEGRADED", "ONLINE"} and redundancy <= 0:
        projected_state = "UNAVAILABLE"
        data_availability = "AT_RISK"
    else:
        projected_state = current_state or "UNKNOWN"
        data_availability = "UNKNOWN"

    return {
        "schema_version": 1,
        "simulation": True,
        "read_only": True,
        "production_mutation": False,
        "destructive_actions": False,
        "available": True,
        "scenario": "drive_failure_now",
        "target": {
            "physical_bay": target.get("physical_bay"),
            "pool": pool_name,
            "zfs_state": target.get("zfs_state"),
            "mapping_source": target.get("mapping_source"),
        },
        "current_pool_state": current_state,
        "projected_pool_state": projected_state,
        "data_availability": data_availability,
        "remaining_redundancy_before": redundancy,
        "remaining_redundancy_after": max(0, redundancy - 1),
        "expected_events": [
            "storage.device_unavailable",
            "storage.pool_degraded",
            "pathfinder.guided_recovery_ready",
        ],
        "operator_message": (
            "Simulation only. No drive, pool, or TrueNAS state has been changed."
        ),
    }
