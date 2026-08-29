"""Read-only replacement-media discovery for Project Lifeline.

The provider combines the current hardware inventory, already-collected ZFS
membership evidence, and read-only block signatures. It never wipes, labels,
partitions, imports, offlines, or attaches media.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .identity import DriveIdentity, DriveIdentityResolver

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


def _identity_relation(
    original_identity: dict[str, Any],
    candidate_identity: DriveIdentity | None,
    *,
    failed_serial_last4: str,
    candidate_serial_last4: str,
) -> str:
    """Classify candidate identity without trusting its Linux device path."""

    original_identity = (
        original_identity
        if isinstance(original_identity, dict)
        else {}
    )
    original_key = _text(original_identity.get("stable_key"))
    original_mode = _text(original_identity.get("mode"))

    candidate_key = (
        candidate_identity.stable_key
        if candidate_identity is not None
        else ""
    )
    candidate_mode = (
        candidate_identity.mode
        if candidate_identity is not None
        else ""
    )

    # Stable hardware identities are directly comparable only when they use
    # the same identity namespace. Runtime device paths are deliberately
    # excluded from this comparison.
    if (
        original_key
        and candidate_key
        and original_mode == candidate_mode
        and original_mode in {"wwn", "serial_model"}
    ):
        return (
            "same"
            if original_key == candidate_key
            else "different"
        )

    # A serial suffix mismatch is sufficient to prove that this is not the
    # original physical disk. A match is conservatively treated as the same
    # disk, even though suffixes alone are not globally unique.
    original_serial_last4 = (
        failed_serial_last4
        or _text(original_identity.get("serial_last4"))
    )
    if original_serial_last4 and candidate_serial_last4:
        return (
            "same"
            if original_serial_last4 == candidate_serial_last4
            else "different"
        )

    return "unknown"


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
        identity_resolver: DriveIdentityResolver | None = None,
    ) -> None:
        self._inventory = inventory
        self._signature_runner = signature_runner or _default_signature_runner
        self._identity_resolver = identity_resolver

    def _inventory_service(self):
        if self._inventory is not None:
            return self._inventory
        from truepanel.hardware.manager import HardwareManager

        self._inventory = HardwareManager().inventory
        return self._inventory

    def _identity_service(self) -> DriveIdentityResolver:
        if self._identity_resolver is None:
            self._identity_resolver = DriveIdentityResolver(
                inventory=self._inventory_service()
            )
        return self._identity_resolver

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
        failed_identity = original_fault.get("drive_identity")
        failed_identity = (
            failed_identity
            if isinstance(failed_identity, dict)
            else {}
        )

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
            model = _text(getattr(item, "model", ""))
            drive = getattr(item, "drive", None)
            capacity = _integer(getattr(drive, "size_bytes", None))

            try:
                candidate_identity = self._identity_service().resolve(
                    {
                        "device": device,
                        "bay": bay,
                        "model": model,
                        "serial_last4": serial_last4,
                        "capacity_bytes": capacity,
                    }
                )
            except (
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
                AttributeError,
            ):
                candidate_identity = None

            identity_relation = _identity_relation(
                failed_identity,
                candidate_identity,
                failed_serial_last4=failed_serial_last4,
                candidate_serial_last4=serial_last4,
            )

            # Replacement discovery is allowed to produce a candidate only
            # when the attached medium can be proven different from the
            # original disk. "same" and "unknown" both fail closed.
            if identity_relation != "different":
                continue

            zfs = zfs_by_device.get(device, {})
            zfs_state = _text(zfs.get("zfs_state")).upper()
            same_path = bool(failed_device and device == failed_device)

            member_of_pool = bool(
                zfs_state in _MEMBER_STATES
                and not (
                    same_path
                    and zfs_state
                    in {"FAULTED", "OFFLINE", "UNAVAIL", "UNAVAILABLE", "REMOVED"}
                )
            )

            ambiguous = bay is None

            results.append(
                {
                    "device": device,
                    "model": model or None,
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
                    "identity_verified_distinct": True,
                    "same_slot_replacement": bool(
                        failed_bay is not None
                        and bay == failed_bay
                    ),
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
