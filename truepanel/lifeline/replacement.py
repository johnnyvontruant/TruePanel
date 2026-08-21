"""Read-only replacement-media discovery for Project Lifeline.

The provider combines the current hardware inventory, already-collected ZFS
membership evidence, and read-only block signatures. It never wipes, labels,
partitions, imports, offlines, or attaches media.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable


_MEMBER_STATES = {
    "ONLINE",
    "DEGRADED",
    "FAULTED",
    "OFFLINE",
    "UNAVAIL",
    "UNAVAILABLE",
    "REMOVED",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _integer(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _default_signature_runner() -> str:
    """Return JSON block-signature metadata without modifying any device."""

    result = subprocess.run(
        [
            "lsblk",
            "--json",
            "--bytes",
            "--output",
            "NAME,TYPE,SIZE,FSTYPE,PTTYPE,MOUNTPOINTS",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10.0,
    )
    return result.stdout if result.returncode == 0 else ""


def parse_block_signatures(text: str) -> dict[str, bool]:
    """Return whole-device names mapped to whether existing data is visible."""

    try:
        payload = json.loads(str(text or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    devices = payload.get("blockdevices") if isinstance(payload, dict) else None
    if not isinstance(devices, list):
        return {}

    results: dict[str, bool] = {}

    def node_has_signature(node: dict[str, Any]) -> bool:
        if _text(node.get("fstype")) or _text(node.get("pttype")):
            return True
        mounts = node.get("mountpoints")
        if isinstance(mounts, list) and any(_text(item) for item in mounts):
            return True
        children = node.get("children")
        if isinstance(children, list):
            return any(
                isinstance(child, dict) and node_has_signature(child)
                for child in children
            )
        return False

    for node in devices:
        if not isinstance(node, dict):
            continue
        name = Path(_text(node.get("name"))).name
        if not name:
            continue
        results[name] = node_has_signature(node)

    return results


class ReplacementCandidateProvider:
    """Discover conservative replacement candidates for one failed member."""

    def __init__(
        self,
        *,
        inventory=None,
        signature_runner: Callable[[], str] | None = None,
    ) -> None:
        self._inventory = inventory
        self._signature_runner = signature_runner or _default_signature_runner

    def _inventory_service(self):
        if self._inventory is not None:
            return self._inventory
        from truepanel.hardware.manager import HardwareManager

        self._inventory = HardwareManager().inventory
        return self._inventory

    def _signatures(self) -> dict[str, bool]:
        try:
            return parse_block_signatures(self._signature_runner())
        except (OSError, RuntimeError, subprocess.SubprocessError):
            return {}

    def candidates(
        self,
        original_fault: dict[str, Any],
        *,
        storage_devices: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        original_fault = original_fault if isinstance(original_fault, dict) else {}
        failed_device = _text(original_fault.get("device"))
        failed_bay = original_fault.get("bay") or original_fault.get("physical_bay")
        failed_serial_last4 = _text(original_fault.get("serial_last4"))
        failed_capacity = _integer(original_fault.get("capacity_bytes"))

        zfs_records = [
            item
            for item in (storage_devices or [])
            if isinstance(item, dict)
        ]
        zfs_by_device = {
            _text(item.get("device")): item
            for item in zfs_records
            if _text(item.get("device"))
        }
        signatures = self._signatures()

        try:
            inventory = self._inventory_service().devices()
        except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
            return []

        results: list[dict[str, Any]] = []
        for item in inventory:
            category = _text(getattr(item, "category", ""))
            if category in {"boot-media", "internal-nvme"}:
                continue
            if category not in {"front-bay", "unassigned"}:
                continue

            device = _text(getattr(item, "device", ""))
            if not device:
                continue
            bay = getattr(item, "physical_bay", None)

            # For a known front-bay fault, Lifeline is intentionally same-slot
            # first. Other media remains invisible until a later workflow can
            # safely model cross-bay replacement and topology changes.
            if failed_bay is not None and bay != failed_bay:
                continue

            serial = _text(getattr(item, "serial", ""))
            serial_last4 = serial[-4:] if serial else ""
            drive = getattr(item, "drive", None)
            capacity = _integer(getattr(drive, "size_bytes", None))
            zfs = zfs_by_device.get(device, {})
            zfs_state = _text(zfs.get("zfs_state")).upper()

            same_path = bool(failed_device and device == failed_device)
            serial_changed = bool(
                failed_serial_last4
                and serial_last4
                and serial_last4 != failed_serial_last4
            )

            member_of_pool = bool(
                zfs_state in _MEMBER_STATES
                and not (
                    same_path
                    and serial_changed
                    and zfs_state
                    in {"FAULTED", "OFFLINE", "UNAVAIL", "UNAVAILABLE", "REMOVED"}
                )
            )

            ambiguous = False
            if not serial_last4:
                ambiguous = True
            if same_path and not serial_changed:
                # A path can be reused after hot-swap. Without a serial change,
                # Lifeline cannot prove this is new replacement media.
                ambiguous = True
            if failed_bay is not None and bay is None:
                ambiguous = True

            results.append(
                {
                    "device": device,
                    "model": _text(getattr(item, "model", "")) or None,
                    "serial_last4": serial_last4 or None,
                    "capacity_bytes": capacity,
                    "minimum_capacity_bytes": failed_capacity,
                    "bay": bay,
                    "category": category,
                    "mapping_source": _text(
                        getattr(item, "mapping_source", "")
                    )
                    or None,
                    "member_of_pool": member_of_pool,
                    "contains_preserved_data": signatures.get(device, True),
                    "ambiguous": ambiguous,
                    "same_slot_replacement": bool(same_path and serial_changed),
                    "zfs_state_at_discovery": zfs_state or None,
                }
            )

        return sorted(
            results,
            key=lambda item: (
                item.get("bay") is None,
                item.get("bay") or 9999,
                str(item.get("device") or ""),
            ),
        )


__all__ = ["ReplacementCandidateProvider", "parse_block_signatures"]
