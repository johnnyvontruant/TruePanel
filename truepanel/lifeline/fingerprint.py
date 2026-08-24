"""Persistent last-known-good drive fingerprints for Project Lifeline.

The fingerprint path is read-only with respect to storage. It correlates a
healthy ZFS leaf GUID to current Linux hardware identity and stores only
TruePanel metadata. It cannot online, offline, replace, wipe, label, partition,
or otherwise mutate a pool or disk.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from truepanel.guidance.storage_evidence import normalize_device, parse_zpool_status


DEFAULT_DRIVE_FINGERPRINT_PATH = Path(
    "/var/lib/truepanel/lifeline/drive-fingerprints.json"
)
_SCHEMA_VERSION = 1
_DEFAULT_REFRESH_SECONDS = 60.0
_TRUSTED_MAPPING_SOURCES = {"kernel"}

_STATUS_ROW = re.compile(
    r"^(?P<indent>\s*)(?P<name>\S+)\s+"
    r"(?P<state>ONLINE|DEGRADED|FAULTED|OFFLINE|UNAVAIL|UNAVAILABLE|REMOVED)\s+"
    r"(?P<read>\d+|-)\s+(?P<write>\d+|-)\s+(?P<cksum>\d+|-)(?:\s+.*)?$"
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _integer(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _default_status_runner(*, guids: bool) -> str:
    command = ["zpool", "status"]
    if guids:
        command.append("-g")
    command.extend(["-L", "-P"])
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=10.0,
    )
    return result.stdout if result.returncode == 0 else ""


def _default_udev_runner(device: str) -> str:
    result = subprocess.run(
        ["udevadm", "info", "--query=property", f"--name={device}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5.0,
    )
    return result.stdout if result.returncode == 0 else ""


def _properties(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in str(text or "").splitlines():
        key, separator, value = line.partition("=")
        if separator and key:
            values[key.strip()] = value.strip()
    return values


def _status_rows(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in str(text or "").splitlines():
        match = _STATUS_ROW.match(raw)
        if not match:
            continue
        rows.append(
            {
                "indent": len(match.group("indent").replace("\t", "        ")),
                "name": match.group("name"),
                "state": match.group("state").upper(),
                "read": match.group("read"),
                "write": match.group("write"),
                "cksum": match.group("cksum"),
            }
        )
    return rows


def _pool_states(text: str) -> dict[str, str]:
    states: dict[str, str] = {}
    pool: str | None = None
    in_config = False
    for raw in str(text or "").splitlines():
        stripped = raw.strip()
        if stripped.startswith("pool:"):
            pool = stripped.split(":", 1)[1].strip()
            in_config = False
            continue
        if stripped == "config:":
            in_config = True
            continue
        if not pool or not in_config:
            continue
        match = _STATUS_ROW.match(raw)
        if match and match.group("name") == pool:
            states[pool] = match.group("state").upper()
            in_config = False
    return states


def _aligned_leaf_guids(
    path_status: str,
    guid_status: str,
) -> dict[str, str]:
    """Map live absolute ZFS leaf paths to GUIDs when both status trees agree."""

    path_rows = _status_rows(path_status)
    guid_rows = _status_rows(guid_status)
    if not path_rows or len(path_rows) != len(guid_rows):
        return {}

    results: dict[str, str] = {}
    for path_row, guid_row in zip(path_rows, guid_rows):
        if (
            path_row["indent"] != guid_row["indent"]
            or path_row["state"] != guid_row["state"]
            or path_row["read"] != guid_row["read"]
            or path_row["write"] != guid_row["write"]
            or path_row["cksum"] != guid_row["cksum"]
        ):
            return {}

        path_name = _text(path_row["name"])
        guid_name = _text(guid_row["name"])
        if not path_name.startswith("/dev/") or not guid_name.isdigit():
            continue
        if int(guid_name) <= 0:
            continue
        results[path_name] = guid_name

    return results


class DriveFingerprintProvider:
    """Collect independently cross-checked fingerprints from healthy ZFS leaves."""

    def __init__(
        self,
        *,
        inventory=None,
        path_status_runner: Callable[[], str] | None = None,
        guid_status_runner: Callable[[], str] | None = None,
        udev_runner: Callable[[str], str] | None = None,
        clock=None,
        refresh_seconds: float = _DEFAULT_REFRESH_SECONDS,
    ) -> None:
        self._inventory = inventory
        self._path_status_runner = path_status_runner or (
            lambda: _default_status_runner(guids=False)
        )
        self._guid_status_runner = guid_status_runner or (
            lambda: _default_status_runner(guids=True)
        )
        self._udev_runner = udev_runner or _default_udev_runner
        self._clock = clock or time.time
        self._refresh_seconds = max(float(refresh_seconds), 0.0)
        self._last_refresh: float | None = None
        self._cached: list[dict[str, Any]] = []

    def _inventory_service(self):
        if self._inventory is not None:
            return self._inventory
        from truepanel.hardware.manager import HardwareManager

        self._inventory = HardwareManager().inventory
        return self._inventory

    def fingerprints(self) -> list[dict[str, Any]]:
        now = float(self._clock())
        if (
            self._last_refresh is not None
            and now - self._last_refresh < self._refresh_seconds
        ):
            return deepcopy(self._cached)

        self._last_refresh = now
        records = self._collect(now)
        self._cached = records
        return deepcopy(records)

    def _collect(self, observed_at: float) -> list[dict[str, Any]]:
        try:
            path_status = self._path_status_runner()
            guid_status = self._guid_status_runner()
        except (OSError, RuntimeError, subprocess.SubprocessError):
            return []

        lowered = str(path_status or "").lower()
        if any(
            marker in lowered
            for marker in (
                "scrub in progress",
                "resilver in progress",
                "resilvering",
            )
        ):
            return []

        pool_states = _pool_states(path_status)
        path_to_guid = _aligned_leaf_guids(path_status, guid_status)
        if not path_to_guid:
            return []

        parsed = parse_zpool_status(path_status)
        parsed_by_name = {
            _text(item.get("zfs_name")): item
            for item in parsed
            if isinstance(item, dict) and _text(item.get("zfs_name"))
        }

        try:
            inventory = self._inventory_service()
            attached = {
                item.device: item
                for item in inventory.devices()
            }
        except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
            return []

        results: list[dict[str, Any]] = []
        for zfs_path, member_guid in path_to_guid.items():
            zfs = parsed_by_name.get(zfs_path)
            if not isinstance(zfs, dict):
                continue
            pool = _text(zfs.get("pool"))
            if pool_states.get(pool) != "ONLINE":
                continue
            if _text(zfs.get("zfs_state")).upper() != "ONLINE":
                continue

            device = normalize_device(zfs_path)
            item = attached.get(device or "")
            if item is None:
                continue
            if _text(getattr(item, "category", "")) != "front-bay":
                continue

            mapping_source = _text(getattr(item, "mapping_source", ""))
            physical_bay = _integer(getattr(item, "physical_bay", None))
            serial = _text(getattr(item, "serial", ""))
            model = _text(getattr(item, "model", ""))
            drive = getattr(item, "drive", None)
            capacity = _integer(getattr(drive, "size_bytes", None))
            if not serial or not physical_bay or not capacity or capacity <= 0:
                continue

            try:
                partition_properties = _properties(self._udev_runner(zfs_path))
                disk_properties = _properties(
                    self._udev_runner(f"/dev/{device}")
                )
            except (OSError, RuntimeError, subprocess.SubprocessError):
                continue

            partuuid = _text(partition_properties.get("ID_PART_ENTRY_UUID"))
            wwn = _text(disk_properties.get("ID_WWN")) or None
            if not partuuid:
                continue

            results.append(
                {
                    "verified": mapping_source in _TRUSTED_MAPPING_SOURCES,
                    "pool": pool,
                    "vdev": zfs.get("vdev"),
                    "vdev_topology": zfs.get("vdev_topology"),
                    "member_guid": member_guid,
                    "partuuid": partuuid,
                    "zfs_path": zfs_path,
                    "device": device,
                    "physical_bay": physical_bay,
                    "mapping_source": mapping_source or None,
                    "enclosure": _text(getattr(item, "enclosure", "")) or None,
                    "model": model or None,
                    "serial": serial,
                    "serial_last4": serial[-4:],
                    "wwn": wwn,
                    "capacity_bytes": capacity,
                    "observed_at": observed_at,
                    "source": "healthy_pool_cross_check",
                }
            )

        return sorted(
            results,
            key=lambda item: (
                str(item.get("pool") or ""),
                int(item.get("physical_bay") or 9999),
                str(item.get("member_guid") or ""),
            ),
        )


class DriveFingerprintStore:
    """Persist last-known-good fingerprints without mutating storage."""

    _IDENTITY_FIELDS = (
        "partuuid",
        "serial",
        "wwn",
        "model",
        "capacity_bytes",
        "physical_bay",
        "mapping_source",
    )

    def __init__(self, path=None, *, clock=None) -> None:
        self.path = Path(path or DEFAULT_DRIVE_FINGERPRINT_PATH)
        self.clock = clock or time.time
        self._state = self._load()

    def _empty(self) -> dict[str, Any]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "fingerprints": {},
        }

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return self._empty()
        if not isinstance(payload, dict) or payload.get("schema_version") != _SCHEMA_VERSION:
            return self._empty()
        if not isinstance(payload.get("fingerprints"), dict):
            payload["fingerprints"] = {}
        return payload

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp-{os.getpid()}")
        encoded = json.dumps(self._state, sort_keys=True, indent=2) + "\n"
        try:
            temporary.write_text(encoded, encoding="utf-8")
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _key(record: dict[str, Any]) -> str | None:
        pool = _text(record.get("pool"))
        member_guid = _text(record.get("member_guid"))
        if not pool or not member_guid or not member_guid.isdigit():
            return None
        return f"{pool}:{member_guid}"

    def record(self, records: list[dict[str, Any]]) -> bool:
        changed = False
        now = float(self.clock())
        fingerprints = self._state["fingerprints"]

        for supplied in records if isinstance(records, list) else []:
            if not isinstance(supplied, dict) or supplied.get("verified") is not True:
                continue
            key = self._key(supplied)
            if key is None:
                continue
            current = fingerprints.get(key)
            incoming = deepcopy(supplied)
            observed_at = float(incoming.get("observed_at", now) or now)

            if not isinstance(current, dict):
                incoming.update(
                    {
                        "first_seen_at": observed_at,
                        "last_seen_at": observed_at,
                        "observations": 1,
                        "conflicted": False,
                    }
                )
                fingerprints[key] = incoming
                changed = True
                continue

            if current.get("conflicted") is True:
                continue

            conflicts = {
                field: {
                    "stored": current.get(field),
                    "observed": incoming.get(field),
                }
                for field in self._IDENTITY_FIELDS
                if current.get(field) not in (None, "")
                and incoming.get(field) not in (None, "")
                and current.get(field) != incoming.get(field)
            }
            if conflicts:
                current["conflicted"] = True
                current["conflict_observed_at"] = observed_at
                current["conflicts"] = conflicts
                changed = True
                continue

            current["last_seen_at"] = max(
                float(current.get("last_seen_at", 0.0) or 0.0),
                observed_at,
            )
            current["observations"] = int(current.get("observations", 0) or 0) + 1
            current["device"] = incoming.get("device")
            current["zfs_path"] = incoming.get("zfs_path")
            current["enclosure"] = incoming.get("enclosure")
            current["source"] = incoming.get("source")
            changed = True

        if changed:
            self._save()
        return changed

    def lookup(self, pool: str, member_guid: str) -> dict[str, Any] | None:
        key = self._key({"pool": pool, "member_guid": member_guid})
        if key is None:
            return None
        record = self._state["fingerprints"].get(key)
        if not isinstance(record, dict):
            return None
        if record.get("verified") is not True or record.get("conflicted") is True:
            return None
        return deepcopy(record)

    def snapshot(self) -> dict[str, Any]:
        records = list(self._state["fingerprints"].values())
        return {
            "schema_version": _SCHEMA_VERSION,
            "metadata_only": True,
            "count": len(records),
            "conflicted": sum(
                1 for item in records
                if isinstance(item, dict) and item.get("conflicted") is True
            ),
        }


__all__ = [
    "DEFAULT_DRIVE_FINGERPRINT_PATH",
    "DriveFingerprintProvider",
    "DriveFingerprintStore",
]
