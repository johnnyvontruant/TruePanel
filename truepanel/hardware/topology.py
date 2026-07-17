"""
Logical hardware topology resolution.

The enclosure controller reports Linux's raw SGPIO/SES view. TopologyResolver
combines that raw view with stable, administrator-configured device identities
to describe the actual physical chassis.

This module is read-only and performs no hardware writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol, Sequence

from .enclosure import EnclosureSlot


class DriveIdentity(Protocol):
    """Minimum drive identity required by the topology resolver."""

    device: str
    serial: str
    model: str


@dataclass(frozen=True)
class FrontBay:
    """Resolved state of one human-facing chassis bay."""

    physical_bay: int
    kernel_slot: int
    installed: bool
    status: str
    device: str
    model: str
    serial: str
    wwid: str
    enclosure: str
    mapping_source: str
    kernel_slot_state: EnclosureSlot

    @property
    def device_path(self) -> str:
        return f"/dev/{self.device}" if self.device else ""

    @property
    def display_name(self) -> str:
        return f"Bay {self.physical_bay}"


class TopologyResolver:
    """
    Resolve Linux enclosure slots into physical chassis bays.

    Configuration uses one-based physical bay numbers:

        hardware:
          topology:
            front_bays:
              5:
                serial: WSD9KX4V
              6:
                serial: WSD9QAWH

    Kernel-discovered devices remain authoritative when present. A configured
    identity fills a slot only when Linux exposes the slot but does not link a
    block device to it.
    """

    def __init__(
        self,
        config: Mapping | None = None,
    ) -> None:
        self.config = dict(config or {})

    def front_bay_overrides(self) -> dict[int, dict]:
        """Return normalized one-based front-bay configuration."""

        configured = self.config.get("front_bays", {})
        normalized: dict[int, dict] = {}

        if not isinstance(configured, Mapping):
            return normalized

        for raw_bay, raw_value in configured.items():
            try:
                bay = int(raw_bay)
            except (TypeError, ValueError):
                continue

            if bay < 1 or not isinstance(raw_value, Mapping):
                continue

            normalized[bay] = dict(raw_value)

        return normalized

    def resolve_front_bays(
        self,
        slots: Iterable[EnclosureSlot],
        drives: Sequence[DriveIdentity],
    ) -> list[FrontBay]:
        """Resolve raw enclosure slots into physical front bays."""

        drive_by_device = {
            drive.device: drive
            for drive in drives
            if drive.device
        }
        drive_by_serial = {
            drive.serial: drive
            for drive in drives
            if drive.serial
        }

        overrides = self.front_bay_overrides()
        resolved: list[FrontBay] = []
        claimed_devices: set[str] = set()

        ordered_slots = sorted(
            slots,
            key=lambda slot: (slot.enclosure, slot.kernel_slot),
        )

        for slot in ordered_slots:
            physical_bay = slot.physical_bay
            mapping_source = "kernel"
            device = slot.device
            model = slot.model
            serial = slot.serial
            installed = slot.installed
            status = slot.status

            kernel_drive = drive_by_device.get(device)

            if kernel_drive is not None:
                model = kernel_drive.model or model
                serial = kernel_drive.serial or serial

            if device:
                claimed_devices.add(device)

            override = overrides.get(physical_bay, {})

            if not device and override:
                configured_drive = self._find_configured_drive(
                    override,
                    drive_by_serial=drive_by_serial,
                    drive_by_device=drive_by_device,
                )

                if (
                    configured_drive is not None
                    and configured_drive.device not in claimed_devices
                ):
                    device = configured_drive.device
                    model = configured_drive.model
                    serial = configured_drive.serial
                    installed = True
                    status = "configured"
                    mapping_source = "configured"
                    claimed_devices.add(device)
                else:
                    mapping_source = "configured-missing"

            resolved.append(
                FrontBay(
                    physical_bay=physical_bay,
                    kernel_slot=slot.kernel_slot,
                    installed=installed,
                    status=status,
                    device=device,
                    model=model,
                    serial=serial,
                    wwid=slot.wwid,
                    enclosure=slot.enclosure,
                    mapping_source=mapping_source,
                    kernel_slot_state=slot,
                )
            )

        return resolved

    @staticmethod
    def _find_configured_drive(
        override: Mapping,
        *,
        drive_by_serial: Mapping[str, DriveIdentity],
        drive_by_device: Mapping[str, DriveIdentity],
    ) -> DriveIdentity | None:
        """
        Resolve a configured identity.

        Serial is preferred because /dev/sdX names are not stable. Device-name
        lookup exists only as a diagnostic fallback for temporary experiments.
        """

        serial = str(override.get("serial", "")).strip()

        if serial:
            return drive_by_serial.get(serial)

        device = str(override.get("device", "")).strip()
        device = device.rsplit("/", 1)[-1]

        if device:
            return drive_by_device.get(device)

        return None


__all__ = [
    "DriveIdentity",
    "FrontBay",
    "TopologyResolver",
]
