"""Resolve ZFS member state to independently verified hardware identity.

The resolver is intentionally read-only and conservative. ZFS identifies pool
membership; TruePanel's storage inventory identifies attached hardware and
physical bays. A bay is published only when the inventory can independently
confirm the normalized ZFS device name.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Callable


_ZFS_ROW = re.compile(
    r"^(?P<indent>\s*)(?P<name>\S+)\s+"
    r"(?P<state>ONLINE|DEGRADED|FAULTED|OFFLINE|UNAVAIL|UNAVAILABLE|REMOVED)\s+"
    r"(?P<read>\d+|-)\s+(?P<write>\d+|-)\s+(?P<cksum>\d+|-)(?P<tail>.*)$"
)
_VDEV = re.compile(r"^(mirror|raidz[123])(?:-|$)", re.IGNORECASE)
_NON_DATA_SECTIONS = {"logs", "cache", "spares", "special", "dedup"}


def _counter(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _historical_path(value: Any) -> str | None:
    text = str(value or "").strip()
    match = re.search(r"\bwas\s+(/dev/\S+)", text)
    return match.group(1) if match else None


def normalize_device(value: Any) -> str | None:
    """Normalize a current ZFS member path to a whole Linux block device.

    Stable aliases under ``/dev/disk`` are logical storage identifiers, not
    Linux whole-device names. They deliberately remain unresolved here unless
    ZFS also supplies a direct historical ``/dev/sdX``-style path. Physical bay
    publication requires an independently present device in inventory.
    """

    text = str(value or "").strip()
    if not text:
        return None

    historical = _historical_path(text)
    if historical:
        text = historical

    if text.startswith("/dev/disk/"):
        return None

    name = Path(text).name
    if not name or name.isdigit():
        return None

    nvme = re.match(r"^(nvme\d+n\d+)(?:p\d+)?$", name)
    if nvme:
        return nvme.group(1)

    mmc = re.match(r"^(mmcblk\d+)(?:p\d+)?$", name)
    if mmc:
        return mmc.group(1)

    disk = re.match(r"^((?:sd|hd|vd|xvd)[a-z]+)(?:\d+)?$", name)
    if disk:
        return disk.group(1)

    return None


def _topology(name: str) -> str | None:
    lowered = name.lower()
    if lowered.startswith("raidz1"):
        return "RAIDZ1"
    if lowered.startswith("raidz2"):
        return "RAIDZ2"
    if lowered.startswith("raidz3"):
        return "RAIDZ3"
    if lowered.startswith("mirror"):
        return "MIRROR"
    return None


def _fault_tolerance(topology: str | None, member_count: int) -> int | None:
    if topology == "RAIDZ1":
        return 1
    if topology == "RAIDZ2":
        return 2
    if topology == "RAIDZ3":
        return 3
    if topology == "MIRROR":
        return max(member_count - 1, 0)
    return None


def parse_zpool_status(text: str) -> list[dict[str, Any]]:
    """Parse data-VDEV members from ``zpool status -L -P`` output."""

    members: list[dict[str, Any]] = []
    pool: str | None = None
    in_config = False
    root_indent: int | None = None
    active_vdev: dict[str, Any] | None = None
    section: str | None = None

    for raw in str(text or "").splitlines():
        stripped = raw.strip()

        if stripped.startswith("pool:"):
            pool = stripped.split(":", 1)[1].strip()
            in_config = False
            root_indent = None
            active_vdev = None
            section = None
            continue

        if stripped == "config:":
            in_config = True
            root_indent = None
            active_vdev = None
            section = None
            continue

        if not in_config or not pool:
            continue

        if stripped.startswith("errors:"):
            in_config = False
            continue

        if stripped.lower() in _NON_DATA_SECTIONS:
            section = stripped.lower()
            active_vdev = None
            continue

        match = _ZFS_ROW.match(raw)
        if not match:
            continue

        indent = len(match.group("indent").replace("\t", "        "))
        name = match.group("name")
        state = match.group("state").upper()

        if name == pool:
            root_indent = indent
            active_vdev = None
            section = None
            continue

        if section is not None:
            if _VDEV.match(name):
                section = None
            else:
                continue

        if _VDEV.match(name):
            active_vdev = {
                "name": name,
                "topology": _topology(name),
                "indent": indent,
                "members": [],
            }
            continue

        if root_indent is None:
            continue

        tail = match.group("tail").strip()
        raw_identity = f"{name} {tail}".strip()
        device = normalize_device(raw_identity)
        historical_path = _historical_path(raw_identity)

        common = {
            "pool": pool,
            "member_id": name,
            "historical_path": historical_path,
            "device": device,
            "zfs_name": name,
            "zfs_state": state,
            "read_errors": _counter(match.group("read")),
            "write_errors": _counter(match.group("write")),
            "checksum_errors": _counter(match.group("cksum")),
        }

        if active_vdev is None:
            if indent <= root_indent:
                continue
            members.append(
                {
                    **common,
                    "vdev": pool,
                    "vdev_topology": None,
                    "remaining_redundancy": None,
                }
            )
            continue

        if indent <= int(active_vdev["indent"]):
            active_vdev = None
            continue

        record = {
            **common,
            "vdev": active_vdev["name"],
            "vdev_topology": active_vdev["topology"],
            "remaining_redundancy": None,
        }
        active_vdev["members"].append(record)
        members.append(record)

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in members:
        topology = record.get("vdev_topology")
        if not topology:
            continue
        grouped.setdefault((record["pool"], record["vdev"]), []).append(record)

    unhealthy = {
        "DEGRADED",
        "FAULTED",
        "OFFLINE",
        "UNAVAIL",
        "UNAVAILABLE",
        "REMOVED",
    }
    for records in grouped.values():
        topology = records[0].get("vdev_topology")
        tolerance = _fault_tolerance(topology, len(records))
        if tolerance is None:
            continue
        failed = sum(1 for item in records if item.get("zfs_state") in unhealthy)
        remaining = max(tolerance - failed, 0)
        for item in records:
            item["remaining_redundancy"] = remaining

    return members


def _default_status_runner() -> str:
    result = subprocess.run(
        ["zpool", "status", "-L", "-P"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10.0,
    )
    return result.stdout if result.returncode == 0 else ""


class StorageRecoveryEvidenceProvider:
    """Join ZFS member evidence to TruePanel's authoritative inventory."""

    def __init__(
        self,
        *,
        inventory=None,
        runner: Callable[[], str] | None = None,
    ) -> None:
        self._inventory = inventory
        self._runner = runner or _default_status_runner

    def _inventory_service(self):
        if self._inventory is not None:
            return self._inventory

        from truepanel.hardware.manager import HardwareManager

        self._inventory = HardwareManager().inventory
        return self._inventory

    def records(self) -> list[dict[str, Any]]:
        try:
            status = self._runner()
        except (OSError, RuntimeError, subprocess.SubprocessError):
            return []

        parsed = parse_zpool_status(status)
        if not parsed:
            return []

        try:
            inventory = self._inventory_service()
            attached = {
                item.device: item
                for item in inventory.devices()
            }
        except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
            attached = {}

        results = []
        for record in parsed:
            payload = dict(record)
            device = payload.get("device")
            item = attached.get(device) if device else None

            payload.update(
                {
                    "physical_bay": getattr(item, "physical_bay", None),
                    "model": getattr(item, "model", None),
                    "serial_last4": (
                        str(getattr(item, "serial", ""))[-4:] or None
                        if item is not None
                        else None
                    ),
                    "capacity_bytes": (
                        getattr(getattr(item, "drive", None), "size_bytes", None)
                        if item is not None
                        else None
                    ),
                    "present": item is not None,
                    "mapping_source": getattr(item, "mapping_source", None),
                    "enclosure": getattr(item, "enclosure", None),
                    "label": getattr(item, "label", None),
                }
            )
            results.append(payload)

        return results


__all__ = [
    "StorageRecoveryEvidenceProvider",
    "normalize_device",
    "parse_zpool_status",
]
