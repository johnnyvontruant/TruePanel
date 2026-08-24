"""Privacy-safe read-only front-bay mirror telemetry for Mission Control."""

from __future__ import annotations

import subprocess
from typing import Any, Callable

from truepanel.guidance.storage_evidence import normalize_device, parse_zpool_status


_FAULT_STATES = {
    "FAULTED",
    "OFFLINE",
    "UNAVAIL",
    "UNAVAILABLE",
    "REMOVED",
}


def _default_status_runner() -> str:
    result = subprocess.run(
        ["zpool", "status", "-L", "-P"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10.0,
    )
    return result.stdout if result.returncode == 0 else ""


def _text(value: Any) -> str:
    return str(value or "").strip()


class BayMirrorProvider:
    """Describe front-bay state without publishing disk identity.

    This provider performs read-only discovery only. Public records deliberately
    omit Linux device names, serial numbers, WWNs, models, partition UUIDs, and
    capacity values. The UI receives only enough evidence to mirror bay lights.
    """

    def __init__(
        self,
        *,
        inventory=None,
        status_runner: Callable[[], str] | None = None,
    ) -> None:
        self._inventory = inventory
        self._status_runner = status_runner or _default_status_runner

    def _inventory_service(self):
        if self._inventory is not None:
            return self._inventory

        from truepanel.hardware.manager import HardwareManager

        self._inventory = HardwareManager().inventory
        return self._inventory

    def snapshot(self) -> dict[str, Any]:
        try:
            front_bays = list(self._inventory_service().front_bays())
        except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
            front_bays = []

        try:
            status_text = self._status_runner()
        except (OSError, RuntimeError, subprocess.SubprocessError):
            status_text = ""

        membership: dict[str, dict[str, Any]] = {}
        if status_text:
            for record in parse_zpool_status(status_text):
                if not isinstance(record, dict):
                    continue
                device = normalize_device(record.get("zfs_name"))
                if not device:
                    continue
                membership[device] = record

        bays: list[dict[str, Any]] = []
        for bay in sorted(
            front_bays,
            key=lambda item: int(getattr(item, "physical_bay", 0) or 0),
        ):
            number = int(getattr(bay, "physical_bay", 0) or 0)
            if number <= 0:
                continue

            installed = bool(getattr(bay, "installed", False))
            mapping_source = _text(getattr(bay, "mapping_source", "")) or "unknown"
            kernel = getattr(bay, "kernel_slot_state", None)
            locate = bool(getattr(kernel, "locate", False)) if kernel is not None else False
            fault = bool(getattr(kernel, "fault", False)) if kernel is not None else False

            pool = None
            zfs_state = None

            if mapping_source == "configured-missing":
                state = "missing"
            elif not installed:
                state = "empty"
            elif locate:
                state = "identify"
            elif fault:
                state = "fault"
            elif not status_text:
                state = "unknown"
            else:
                member = membership.get(_text(getattr(bay, "device", "")))
                if member is None:
                    state = "present"
                else:
                    pool = _text(member.get("pool")) or None
                    zfs_state = _text(member.get("zfs_state")).upper() or None
                    if zfs_state == "ONLINE":
                        state = "online"
                    elif zfs_state == "DEGRADED":
                        state = "attention"
                    elif zfs_state in _FAULT_STATES:
                        state = "fault"
                    else:
                        state = "attention"

            bays.append(
                {
                    "bay": number,
                    "state": state,
                    "installed": installed,
                    "pool": pool,
                    "zfs_state": zfs_state,
                    "mapping_source": mapping_source,
                }
            )

        return {
            "schema_version": 1,
            "read_only_hardware": True,
            "privacy_safe": True,
            "available": bool(bays),
            "count": len(bays),
            "bays": bays,
        }


__all__ = ["BayMirrorProvider"]
