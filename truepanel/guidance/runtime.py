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


def _smart_runtime_severity(record: dict[str, Any]) -> str:
    health = _text(record.get("health")).upper()
    warning = _text(record.get("critical_warning")).lower()

    if (
        health == "FAILED"
        or _integer(record.get("pending")) > 0
        or _integer(record.get("offline_uncorrectable")) > 0
        or _integer(record.get("media_errors")) > 0
        or warning not in {"", "0", "0x00", "0x0"}
    ):
        return "critical"

    return "caution"


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

        severity = _smart_runtime_severity(record)
        payload = _active_payload(
            "storage.smart_warning",
            evidence=evidence,
            phase="diagnose",
            blocked_by=blocked,
        )
        payload["severity"] = severity

        if severity == "critical":
            payload["title"] = "Critical drive-health evidence detected"
            payload["summary"] = (
                "Raw SMART evidence indicates active media degradation even "
                "if the vendor self-assessment and ZFS pool state still report "
                "PASSED or ONLINE."
            )
            payload["runtime"]["disposition"] = "prepare_replacement"

        results.append(payload)

    return results


def _faulted_device_guidance(storage: dict[str, Any]) -> list[dict[str, Any]]:
    """Publish member-specific repair guidance when rich evidence is available.

    A missing member can remain logically identified by ZFS even when no
    current Linux block device exists. Logical member identity is therefore
    kept separate from physical device/bay identity and cannot unlock physical
    service on its own.
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
        member_id = record.get("member_id") or record.get("zfs_name")
        device = record.get("device") or record.get("drive")
        evidence = {
            "pool": record.get("pool"),
            "vdev": record.get("vdev"),
            "vdev_topology": record.get("vdev_topology"),
            "remaining_redundancy": record.get("remaining_redundancy"),
            "member_id": member_id,
            "historical_path": record.get("historical_path"),
            "bay": bay,
            "device": device,
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
        if not evidence["pool"] or not evidence["vdev"] or not member_id:
            blocked.append("member_identity_not_verified")
        if not evidence["vdev_topology"]:
            blocked.append("vdev_topology_not_verified")
        if evidence["remaining_redundancy"] is None:
            blocked.append("remaining_redundancy_not_verified")
        if not device:
            blocked.append("device_not_verified")
        if not bay:
            blocked.append("physical_bay_not_verified")
        if evidence["capacity_bytes"] is None:
            blocked.append("capacity_not_verified")

        blocked.extend(
            (
                "chassis_service_procedure_not_verified",
                "backup_acknowledgement_required",
                "replacement_candidate_not_validated",
            )
        )

        if activity["resilver_running"]:
            phase = "monitor_recovery"
        elif not device or not bay:
            phase = "identify"
        else:
            phase = "prepare_repair"

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


def _fan_stall_guidance(fans: dict[str, Any]) -> list[dict[str, Any]]:
    """Publish a fan-stall card only for explicitly monitored channels."""

    if not fans.get("available"):
        return []

    channels = [
        channel
        for channel in _list(fans.get("channels"))
        if isinstance(channel, dict)
    ]
    monitored = [
        channel
        for channel in channels
        if channel.get("monitored") is True
    ]
    healthy_rpm = [
        {
            "label": _text(channel.get("label")),
            "rpm": _integer(channel.get("rpm")),
        }
        for channel in monitored
        if channel.get("alarm") is not True
        and _integer(channel.get("rpm")) > 0
    ]

    results: list[dict[str, Any]] = []
    for channel in monitored:
        rpm = _integer(channel.get("rpm"))
        if channel.get("alarm") is not True and rpm > 0:
            continue

        evidence = {
            "fan_label": _text(channel.get("label"))
            or f"Fan {channel.get('number', '?')}",
            "fan_channel": channel.get("number") or channel.get("channel"),
            "current_rpm": rpm,
            "expected_rpm_range": channel.get("expected_rpm_range"),
            "failure_observations": channel.get("failure_observations")
            or channel.get("consecutive_failures"),
            "other_fan_rpm": healthy_rpm,
            "cpu_temperature_c": fans.get("cpu_temperature_c"),
            "system_temperature_c": fans.get("system_temperature_c"),
            "telemetry_age_seconds": fans.get("age_seconds"),
        }

        results.append(
            _active_payload(
                "cooling.fan_stall",
                evidence=evidence,
                phase="diagnose",
                blocked_by=(
                    "physical_inspection_required",
                    "model_service_procedure_required",
                ),
            )
        )

    return results


def _network_link_guidance(network: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Guide only a verified primary-link loss; unused LAN ports stay silent."""

    interfaces = [
        interface
        for interface in network
        if isinstance(interface, dict)
    ]
    reachable = [
        _text(interface.get("label") or interface.get("name"))
        for interface in interfaces
        if interface.get("link_up") is True
    ]
    tailscale_reachable = any(
        _text(interface.get("kind")).lower() == "tailscale"
        and interface.get("link_up") is True
        for interface in interfaces
    )

    results: list[dict[str, Any]] = []
    for interface in interfaces:
        if interface.get("primary") is not True:
            continue
        if interface.get("link_up") is True:
            continue

        evidence = {
            "interface": interface.get("name"),
            "label": interface.get("label"),
            "link_up": bool(interface.get("link_up")),
            "operstate": interface.get("operstate"),
            "address": interface.get("address"),
            "primary": True,
            "other_reachable_interfaces": reachable,
            "tailscale_reachable": tailscale_reachable,
        }

        results.append(
            _active_payload(
                "network.link_down",
                evidence=evidence,
                phase="diagnose",
                blocked_by=(
                    "peer_port_not_verified",
                    "cable_path_not_verified",
                ),
            )
        )

    return results


def _front_panel_guidance(lcd: dict[str, Any]) -> list[dict[str, Any]]:
    """Publish front-panel recovery guidance without implying NAS failure."""

    reader = _dict(lcd.get("reader"))
    unavailable = not bool(lcd.get("available"))
    reader_unhealthy = (
        reader.get("healthy") is False
        or reader.get("connected") is False
    )

    if not unavailable and not reader_unhealthy:
        return []

    evidence = {
        "serial_device": reader.get("port"),
        "reader_connected": reader.get("connected"),
        "last_successful_io": reader.get("last_healthy_at"),
        "dispatcher_alive": reader.get("dispatcher_alive"),
        "mission_control_reachable": True,
    }

    return [
        _active_payload(
            "front_panel.lcd_unavailable",
            evidence=evidence,
            phase="diagnose",
            blocked_by=(
                "serial_path_not_verified",
                "hardware_inspection_not_required_yet",
            ),
        )
    ]


def _stale_telemetry_guidance(fans: dict[str, Any]) -> list[dict[str, Any]]:
    """Surface an explicit Host thermal freshness failure without inference."""

    control = _dict(fans.get("control"))
    reason = _text(
        control.get("thermal_control_reason")
        or control.get("last_reason")
    )
    stale = (
        control.get("thermal_telemetry_valid") is False
        and "stale" in reason.lower()
    )
    if not stale:
        return []

    evidence = {
        "telemetry_fresh": False,
        "missing_domains": ["thermal"],
        "host_agent_state": control.get("thermal_control_state"),
        "control_authority": control.get("control_authority"),
        "safety_hold": control.get("safety_hold"),
        "reason": reason,
    }
    return [
        _active_payload(
            "telemetry.stale",
            evidence=evidence,
            phase="diagnose",
            blocked_by=("fresh_telemetry_required",),
        )
    ]


def guidance_for_snapshot(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return active operator guidance for an existing Mission Control snapshot.

    The adapter intentionally errs toward diagnosis. It only emits a
    member-specific disk-fault procedure when the snapshot itself contains a
    faulted member; a DEGRADED pool or SMART warning alone never becomes a
    guessed physical-drive replacement. Non-storage guidance is similarly
    evidence-bound: only monitored fan faults, a verified primary-link loss,
    or an explicitly present unavailable/unhealthy LCD domain activate cards.
    """

    storage = _dict(payload.get("storage"))
    fans = _dict(payload.get("fans"))
    network = _list(payload.get("network"))
    lcd = _dict(payload.get("lcd"))

    guidance = []
    guidance.extend(_faulted_device_guidance(storage))
    guidance.extend(_pool_guidance(storage))
    guidance.extend(_smart_guidance(storage))
    guidance.extend(_fan_stall_guidance(fans))
    guidance.extend(_stale_telemetry_guidance(fans))
    guidance.extend(_network_link_guidance(network))
    if "lcd" in payload:
        guidance.extend(_front_panel_guidance(lcd))
    return guidance


__all__ = ["guidance_for_snapshot"]
