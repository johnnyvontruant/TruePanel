"""
Linux enclosure and SGPIO discovery.

Provides a read-only abstraction over Linux's standardized enclosure
interface beneath /sys/class/enclosure.

Mission 4.4A intentionally performs no sysfs writes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_ENCLOSURE_ROOT = Path("/sys/class/enclosure")
_SLOT_PATTERN = re.compile(r"^Slot\s+(\d+)$", re.IGNORECASE)


def _read_text(path: Path, default: str = "") -> str:
    """Read and normalize a small sysfs text attribute."""

    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except (FileNotFoundError, PermissionError, IsADirectoryError, OSError):
        return default


def _read_bool(path: Path) -> bool:
    """Interpret a sysfs boolean attribute."""

    return _read_text(path).lower() in {"1", "yes", "true", "on", "enabled"}


def _read_vpd_serial(path: Path) -> str:
    """
    Extract a printable serial number from SCSI VPD page 0x80.

    Sysfs exposes vpd_pg80 as a binary page containing a short header
    followed by the device serial. Some kernels return the raw binary
    payload rather than plain text.
    """

    try:
        data = path.read_bytes()
    except (FileNotFoundError, PermissionError, IsADirectoryError, OSError):
        return ""

    if len(data) >= 4:
        declared_length = int.from_bytes(data[2:4], byteorder="big")
        payload = data[4 : 4 + declared_length]

        if payload:
            value = payload.decode("ascii", errors="ignore").strip()
            if value:
                return value

    return "".join(
        chr(byte)
        for byte in data
        if 32 <= byte <= 126
    ).strip()


def _find_block_device(device_path: Path) -> str:
    """
    Resolve the Linux block-device name associated with an enclosure slot.

    A normal sysfs topology resembles:

        Slot 00/device/block/sda

    The defensive recursive fallback supports minor kernel layout variations.
    """

    block_path = device_path / "block"

    try:
        direct_devices = sorted(
            child.name
            for child in block_path.iterdir()
            if child.name
        )
    except (FileNotFoundError, PermissionError, NotADirectoryError, OSError):
        direct_devices = []

    if direct_devices:
        return direct_devices[0]

    try:
        candidates = sorted(
            path.name
            for path in device_path.glob("**/block/*")
            if path.name
        )
    except (PermissionError, OSError):
        candidates = []

    return candidates[0] if candidates else ""


@dataclass(frozen=True)
class EnclosureSlot:
    """Read-only snapshot of one physical enclosure slot."""

    number: int
    installed: bool
    status: str
    model: str
    serial: str
    wwid: str
    device: str
    locate: bool
    fault: bool
    active: bool
    enclosure: str
    sysfs_path: Path

    @property
    def device_path(self) -> str:
        """Return a conventional /dev path when a block device is present."""

        return f"/dev/{self.device}" if self.device else ""

    @property
    def display_name(self) -> str:
        """Return a human-friendly bay name."""

        return f"Bay {self.number}"


class EnclosureController:
    """
    Discover Linux SES/SGPIO enclosures through sysfs.

    This controller is strictly read-only. LED control will be introduced
    separately behind explicit safety controls in Mission 4.4C.
    """

    def __init__(
        self,
        root: str | Path = DEFAULT_ENCLOSURE_ROOT,
    ) -> None:
        self.root = Path(root)

    def available(self) -> bool:
        """Return True when at least one enclosure is exposed."""

        return bool(self.enclosures())

    def enclosures(self) -> list[Path]:
        """Return discovered enclosure paths in stable order."""

        try:
            paths = [
                path
                for path in self.root.iterdir()
                if path.is_dir()
            ]
        except (FileNotFoundError, PermissionError, NotADirectoryError, OSError):
            return []

        return sorted(paths, key=lambda path: path.name)

    def slots(self) -> list[EnclosureSlot]:
        """Return snapshots of all slots across all discovered enclosures."""

        discovered: list[EnclosureSlot] = []

        for enclosure_path in self.enclosures():
            discovered.extend(self._slots_for_enclosure(enclosure_path))

        return sorted(
            discovered,
            key=lambda slot: (slot.enclosure, slot.number),
        )

    def populated_slots(self) -> list[EnclosureSlot]:
        """Return only slots containing a device."""

        return [slot for slot in self.slots() if slot.installed]

    def empty_slots(self) -> list[EnclosureSlot]:
        """Return only slots reported as empty."""

        return [slot for slot in self.slots() if not slot.installed]

    def get_slot(
        self,
        number: int,
        enclosure: str | None = None,
    ) -> EnclosureSlot | None:
        """
        Find a slot by number.

        When multiple enclosures exist, enclosure may be supplied to
        disambiguate the request.
        """

        for slot in self.slots():
            if slot.number != number:
                continue

            if enclosure is not None and slot.enclosure != enclosure:
                continue

            return slot

        return None

    def find_device(self, device: str) -> EnclosureSlot | None:
        """
        Find the physical slot associated with a Linux block device.

        Accepts either ``sda`` or ``/dev/sda``.
        """

        normalized = Path(device).name

        for slot in self.slots():
            if slot.device == normalized:
                return slot

        return None

    def _slots_for_enclosure(
        self,
        enclosure_path: Path,
    ) -> Iterable[EnclosureSlot]:
        entries: list[tuple[int, Path]] = []

        try:
            children = list(enclosure_path.iterdir())
        except (FileNotFoundError, PermissionError, NotADirectoryError, OSError):
            return []

        for path in children:
            match = _SLOT_PATTERN.match(path.name)

            if match is None or not path.is_dir():
                continue

            entries.append((int(match.group(1)), path))

        return [
            self._read_slot(
                enclosure_name=enclosure_path.name,
                slot_number=number,
                slot_path=path,
            )
            for number, path in sorted(entries)
        ]

    @staticmethod
    def _read_slot(
        enclosure_name: str,
        slot_number: int,
        slot_path: Path,
    ) -> EnclosureSlot:
        device_path = slot_path / "device"

        status = _read_text(slot_path / "status", default="unknown")
        normalized_status = status.lower()

        block_device = _find_block_device(device_path)

        device_present = device_path.exists() and (
            bool(block_device)
            or bool(_read_text(device_path / "model"))
            or bool(_read_text(device_path / "wwid"))
        )

        installed = (
            normalized_status not in {
                "",
                "not installed",
                "not present",
                "empty",
                "unavailable",
            }
            and device_present
        )

        return EnclosureSlot(
            number=slot_number,
            installed=installed,
            status=status,
            model=_read_text(device_path / "model"),
            serial=_read_vpd_serial(device_path / "vpd_pg80"),
            wwid=_read_text(device_path / "wwid"),
            device=block_device,
            locate=_read_bool(slot_path / "locate"),
            fault=_read_bool(slot_path / "fault"),
            active=_read_bool(slot_path / "active"),
            enclosure=enclosure_name,
            sysfs_path=slot_path,
        )


__all__ = [
    "DEFAULT_ENCLOSURE_ROOT",
    "EnclosureController",
    "EnclosureSlot",
]
