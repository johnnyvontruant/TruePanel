"""Bind live Mission Control telemetry to operator-guidance procedures.

This module is deliberately read-only. It decides which guidance cards are
relevant to a snapshot and publishes the evidence that supports them. It does
not offline devices, identify bays, replace pool members, or perform any other
hardware/storage action.
"""

from __future__ import annotations

from typing import Any

from .catalog import guidance_payload


_UNHEALTHY_POOL_STATES = {
    "DEGRADED",
    "FAULTED",
    "OFFLINE",
    "REMOVED",
    "SUSPENDED",
    "UNAVAIL",
    "UNAVAILABLE",
}
_FAULTED_DEVICE_STATES = {"FAULTED", "UNAVAIL", "UNAVAILABLE"}


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


def _zfs_activity(storage: dict[str, Any]) -> dict[str, Any]:
    activity = _dict(storage.get("zfs_activity"))
    return {
        "scrub_running": bool(activity.get("scrub_running", False)),
        "resilver_running": bool(activity.get("resilver_running", False)),
        "percent": activity.get("percent"),
        "remaining": activity.get("remaining"),
        "status_line": _text(activity.get("status_line")),
        "problem": bool(activity.get("problem", False)),
        "problem_line": _text(activity.get("problem_line")),
    }


def _active_payload(
    code: str,
    *,
    evidence: dict[str, Any],
    phase: str,
    blocked_by: list[str] | tuple[str, ...] = (),
    physical_service_ready: bool = False,
    destructive_actions_ready: bool = False,
) -> dict[str, Any]:
    payload = guidance_payload(code)
    payload["runtime"] = {
        "active": True,
        "phase": phase,
        "evidence": evidence,
        "action_gate": {
            "safe_checks": True,
            "physical_service_ready": bool(physical_service_ready),
            "destructive_actions_ready": bool(destructive_actions_ready),
            "blocked_by": list(blocked_by),
        },
    }
    return payload


def _pool_guidance(storage: dict[str, Any]) -> list[dict[str, Any]]:
    activity = _zfs_activity(storage)
    results: list[dict[str, Any]] = []

    for pool in _list(storage.get("pools")):
        if not isinstance(pool, dict):
            continue

        state = _text(pool.get("health") or pool.get("state")).upper()
        if state not in _UNHEALTHY_POOL_STATES:
            continue

        evidence = {
            "pool": _text(pool.get("name")),
            "pool_state": state,
            "affected_vdevs": pool.get("affected_vdevs"),
            "vdev_topology": pool.get("vdev_topology"),
            "remaining_redundancy": pool.get("remaining_redundancy"),
            "resilver_state": activity,
            "affected_bays": pool.get("affected_bays"),
        }

        blocked = []
        if not evidence["affected_vdevs"]:
            blocked.append("affected_vdev_not_identified")
        if not evidence["vdev_topology"]:
            blocked.append("vdev_topology_not_verified")
        if evidence["remaining_redundancy"] is None:
            blocked.append("remaining_redundancy_not_verified")
        if not evidence["affected_bays"]:
            blocked.append("physical_bay_not_identified")

        phase = (
            "monitor_recovery"
            if activity["resilver_running"]
            else "diagnose"
        )

        results.append(
            _active_payload(
                "storage.pool_degraded",
                evidence=evidence,
                phase=phase,
                blocked_by=blocked,
            )
        )

    return results


def _smart_warning(record: dict[str, Any]) -> bool:
    health = _text(record.get("health")).upper()
    if health == "FAILED":
        return True

    for key in (
        "reallocated",
        "pending",
        "offline_uncorrectable",
        "reported_uncorrect",
        "media_errors",
    ):
        if _integer(record.get(key)) > 0:
            return True

    warning = _text(record.get("critical_warning")).lower()
    return warning not in {"", "0", "0x00", "0x0"}


def _smart_guidance(storage: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for record in _list(storage.get("smart")):
        if not isinstance(record, dict) or not _smart_warning(record):
            continue

        evidence = {
            "pool": record.get("pool"),
            "vdev": record.get("vdev"),
            "bay": record.get("bay") or record.get("physical_bay"),
            "device": record.get("device") or record.get("drive"),
            "model": record.get("model"),
            "serial_last4": record.get("serial_last4"),
            "smart_health": record.get("health"),
            "reallocated": _integer(record.get("reallocated")),
            "pending": _integer(record.get("pending")),
            "offline_uncorrectable": _integer(
                record.get("offline_uncorrectable")
            ),
            "reported_uncorrect": _integer(record.get("reported_uncorrect")),
            "media_errors": _integer(record.get("media_errors")),
            "critical_warning": record.get("critical_warning"),
            "zfs_state": record.get("zfs_state"),
        }

        blocked = []
        if not evidence["pool"] or not evidence["vdev"]:
            blocked.append("zfs_membership_not_verified")
        if not evidence["bay"]:
            blocked.append("physical_bay_not_identified")
        if not evidence["zfs_state"]:
            blocked.append("zfs_state_not_verified")

        results.append(
            _active_payload(
                "storage.smart_warning",
                evidence=evidence,
                phase="diagnose",
                blocked_by=blocked,
            )
        )

    return results


def _faulted_device_guidance(storage: dict[str, Any]) -> list[dict[str, Any]]:
    """Publish member-specific repair guidance when rich evidence is available.

    ``storage.devices`` is an additive forward-compatible contract. Current
    collector snapshots may not populate it yet; in that case a degraded pool
    remains in diagnosis-only guidance and TruePanel never guesses a bay.
    """

    results: list[dict[str, Any]] = []
    activity = _zfs_activity(storage)

    for record in _list(storage.get("devices")):
        if not isinstance(record, dict):
            continue

        zfs_state = _text(record.get("zfs_state") or record.get("state")).upper()
        if zfs_state not in _FAULTED_DEVICE_STATES:
            continue

        bay = record.get("bay") or record.get("physical_bay")
        evidence = {
            "pool": record.get("pool"),
            "vdev": record.get("vdev"),
            "vdev_topology": record.get("vdev_topology"),
            "remaining_redundancy": record.get("remaining_redundancy"),
            "bay": bay,
            "device": record.get("device") or record.get("drive"),
            "model": record.get("model"),
            "capacity_bytes": record.get("capacity_bytes"),
            "present": record.get("present"),
            "zfs_state": zfs_state,
            "read_errors": record.get("read_errors"),
            "write_errors": record.get("write_errors"),
            "checksum_errors": record.get("checksum_errors"),
            "resilver_state": activity,
        }

        blocked = []
        required = (
            ("pool", evidence["pool"]),
            ("vdev", evidence["vdev"]),
            ("vdev_topology", evidence["vdev_topology"]),
            ("remaining_redundancy", evidence["remaining_redundancy"]),
            ("physical_bay", evidence["bay"]),
            ("device", evidence["device"]),
            ("capacity", evidence["capacity_bytes"]),
        )
        for name, value in required:
            if value is None or value == "":
                blocked.append(f"{name}_not_verified")

        # Even complete fault evidence is not enough to authorize replacement.
        # We still need a verified chassis procedure, backup acknowledgement,
        # and a validated replacement candidate before destructive actions.
        blocked.extend(
            (
                "chassis_service_procedure_not_verified",
                "backup_acknowledgement_required",
                "replacement_candidate_not_validated",
            )
        )

        phase = (
            "monitor_recovery"
            if activity["resilver_running"]
            else "prepare_repair"
        )

        results.append(
            _active_payload(
                "storage.disk_faulted",
                evidence=evidence,
                phase=phase,
                blocked_by=blocked,
                physical_service_ready=False,
                destructive_actions_ready=False,
            )
        )

    return results


def guidance_for_snapshot(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return active operator guidance for an existing Mission Control snapshot.

    The adapter intentionally errs toward diagnosis. It only emits a
    member-specific disk-fault procedure when the snapshot itself contains a
    faulted member; a DEGRADED pool or SMART warning alone never becomes a
    guessed physical-drive replacement.
    """

    storage = _dict(payload.get("storage"))
    guidance = []
    guidance.extend(_faulted_device_guidance(storage))
    guidance.extend(_pool_guidance(storage))
    guidance.extend(_smart_guidance(storage))
    return guidance


__all__ = ["guidance_for_snapshot"]
