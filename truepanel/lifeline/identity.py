"""Stable, privacy-safe drive identity for Project Lifeline.

Linux block-device names such as ``sda`` are runtime addresses, not hardware
identity.  This module resolves an attached disk to an opaque stable token from
read-only hardware evidence while keeping raw serial numbers and WWNs out of
Lifeline's persisted/public session ledger.

The resolver has no storage mutation authority.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from truepanel.guidance.storage_evidence import normalize_device


_OPAQUE_TOKEN_HEX = 24


def _text(value: Any) -> str:
    return str(value or "").strip()


def _integer(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _digest(namespace: str, *parts: Any) -> str:
    material = "\x00".join(
        [namespace, *(_text(part).lower() for part in parts)]
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:_OPAQUE_TOKEN_HEX]


def _properties(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in str(text or "").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip():
            values[key.strip()] = value.strip()
    return values


def _default_udev_runner(device: str) -> str:
    result = subprocess.run(
        ["udevadm", "info", "--query=property", f"--name=/dev/{device}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5.0,
    )
    return result.stdout if result.returncode == 0 else ""


def _models_compatible(left: Any, right: Any) -> bool:
    left_text = _text(left).upper()
    right_text = _text(right).upper()
    if not left_text or not right_text:
        return True
    return (
        left_text == right_text
        or left_text.startswith(right_text)
        or right_text.startswith(left_text)
    )


def _stable_member_identity(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    if text.isdigit():
        return text
    if text.startswith(("/dev/disk/by-id/", "/dev/disk/by-partuuid/")):
        return text
    return None


@dataclass(frozen=True)
class DriveIdentity:
    """One privacy-safe identity decision for a drive recovery subject."""

    stable_key: str
    mode: str
    confidence: str
    source: str
    token: str
    device: str | None = None
    bay: int | None = None
    model: str | None = None
    serial_last4: str | None = None
    capacity_bytes: int | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "stable_key": self.stable_key,
            "mode": self.mode,
            "confidence": self.confidence,
            "source": self.source,
            "token": self.token,
            "device": self.device,
            "bay": self.bay,
            "model": self.model,
            "serial_last4": self.serial_last4,
            "capacity_bytes": self.capacity_bytes,
            "raw_serial_exposed": False,
            "raw_wwn_exposed": False,
        }


class DriveIdentityResolver:
    """Resolve current drive evidence to a stable opaque identity token."""

    def __init__(
        self,
        *,
        inventory=None,
        udev_runner: Callable[[str], str] | None = None,
    ) -> None:
        self._inventory = inventory
        self._udev_runner = udev_runner or _default_udev_runner

    def _inventory_service(self):
        if self._inventory is not None:
            return self._inventory
        from truepanel.hardware.manager import HardwareManager

        self._inventory = HardwareManager().inventory
        return self._inventory

    @staticmethod
    def _fallback(evidence: dict[str, Any]) -> DriveIdentity | None:
        device = normalize_device(
            evidence.get("device") or evidence.get("member_id")
        )
        bay = _integer(evidence.get("bay") or evidence.get("physical_bay"))
        model = _text(evidence.get("model")) or None
        serial_last4 = _text(evidence.get("serial_last4")) or None
        capacity = _integer(evidence.get("capacity_bytes"))

        member = _stable_member_identity(
            evidence.get("member_guid")
            or evidence.get("guid")
            or evidence.get("zfs_guid")
            or evidence.get("member_id")
            or evidence.get("zfs_name")
        )
        if member:
            token = _digest("zfs-member", member)
            return DriveIdentity(
                stable_key=f"zfs:{token}",
                mode="zfs_member",
                confidence="high",
                source="zfs_stable_member",
                token=token,
                device=device,
                bay=bay,
                model=model,
                serial_last4=serial_last4,
                capacity_bytes=capacity,
            )

        pool = _text(evidence.get("pool"))
        vdev = _text(evidence.get("vdev"))
        if pool and vdev and bay and model and serial_last4:
            token = _digest(
                "correlated-drive",
                pool,
                vdev,
                bay,
                model,
                serial_last4,
                capacity or "",
            )
            return DriveIdentity(
                stable_key=f"correlated:{token}",
                mode="correlated_evidence",
                confidence="medium",
                source="bay_model_serial_suffix",
                token=token,
                device=device,
                bay=bay,
                model=model,
                serial_last4=serial_last4,
                capacity_bytes=capacity,
            )

        legacy = device or _text(evidence.get("member_id") or evidence.get("zfs_name"))
        if legacy:
            token = _digest("legacy-runtime-address", legacy)
            return DriveIdentity(
                stable_key=f"legacy:{token}",
                mode="legacy_runtime_address",
                confidence="low",
                source="runtime_address_fallback",
                token=token,
                device=device,
                bay=bay,
                model=model,
                serial_last4=serial_last4,
                capacity_bytes=capacity,
            )
        return None

    def resolve(self, evidence: dict[str, Any]) -> DriveIdentity | None:
        evidence = evidence if isinstance(evidence, dict) else {}
        device = normalize_device(
            evidence.get("device") or evidence.get("member_id")
        )
        if not device:
            return self._fallback(evidence)

        try:
            item = self._inventory_service().find_device(device)
        except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
            item = None
        if item is None:
            return self._fallback(evidence)

        serial = _text(getattr(item, "serial", ""))
        model = _text(getattr(item, "model", ""))
        bay = _integer(getattr(item, "physical_bay", None))
        capacity = _integer(getattr(getattr(item, "drive", None), "size_bytes", None))

        expected_serial_last4 = _text(evidence.get("serial_last4"))
        expected_bay = _integer(evidence.get("bay") or evidence.get("physical_bay"))
        expected_capacity = _integer(evidence.get("capacity_bytes"))
        if expected_serial_last4 and (
            not serial or serial[-4:] != expected_serial_last4
        ):
            return self._fallback(evidence)
        if expected_bay is not None and bay is not None and expected_bay != bay:
            return self._fallback(evidence)
        if not _models_compatible(evidence.get("model"), model):
            return self._fallback(evidence)
        if (
            expected_capacity is not None
            and capacity is not None
            and expected_capacity != capacity
        ):
            return self._fallback(evidence)

        try:
            properties = _properties(self._udev_runner(device))
        except (OSError, RuntimeError, subprocess.SubprocessError):
            properties = {}
        wwn = _text(properties.get("ID_WWN") or properties.get("ID_WWN_WITH_EXTENSION"))

        if wwn:
            token = _digest("wwn", wwn)
            return DriveIdentity(
                stable_key=f"wwn:{token}",
                mode="wwn",
                confidence="very_high",
                source="udev_wwn_cross_checked_inventory",
                token=token,
                device=device,
                bay=bay,
                model=model or None,
                serial_last4=serial[-4:] if serial else None,
                capacity_bytes=capacity,
            )

        if serial:
            token = _digest("serial-model", serial, model)
            return DriveIdentity(
                stable_key=f"serial:{token}",
                mode="serial_model",
                confidence="high",
                source="inventory_serial_cross_checked",
                token=token,
                device=device,
                bay=bay,
                model=model or None,
                serial_last4=serial[-4:],
                capacity_bytes=capacity,
            )

        return self._fallback(evidence)


__all__ = ["DriveIdentity", "DriveIdentityResolver"]
