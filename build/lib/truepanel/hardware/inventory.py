"""
TruePanel storage inventory.

StorageInventory combines raw Linux block-device discovery, enclosure slots,
and logical topology configuration into one authoritative storage view.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .enclosure import EnclosureController
from .topology import FrontBay, TopologyResolver


DEFAULT_BLOCK_ROOT = Path("/sys/class/block")


def _read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except (FileNotFoundError, PermissionError, IsADirectoryError, OSError):
        return default


def _read_int(path: Path, default: int = 0) -> int:
    try:
        return int(_read_text(path, str(default)))
    except ValueError:
        return default


def _read_vpd_serial(path: Path) -> str:
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


def _read_ancestor_serial(path: Path) -> str:
    """
    Find a serial exposed by a parent hardware device.

    USB mass-storage devices commonly publish their serial on the USB device
    node rather than the child SCSI disk node.
    """

    try:
        current = path.resolve()
    except OSError:
        current = path

    for parent in (current, *current.parents):
        serial = _read_text(parent / "serial")

        if serial:
            return serial

        if parent == Path("/sys"):
            break

    return ""


@dataclass(frozen=True)
class Drive:
    """Read-only snapshot of one whole Linux block device."""

    device: str
    model: str
    serial: str
    transport: str
    removable: bool
    size_bytes: int
    sysfs_path: Path

    @property
    def device_path(self) -> str:
        return f"/dev/{self.device}"


@dataclass(frozen=True)
class StorageDevice:
    """One drive placed into TruePanel's logical storage topology."""

    drive: Drive
    category: str
    label: str
    physical_bay: int | None = None
    kernel_slot: int | None = None
    enclosure: str = ""
    mapping_source: str = "automatic"

    @property
    def device(self) -> str:
        return self.drive.device

    @property
    def device_path(self) -> str:
        return self.drive.device_path

    @property
    def model(self) -> str:
        return self.drive.model

    @property
    def serial(self) -> str:
        return self.drive.serial


class StorageInventory:
    """
    Build a complete logical inventory of attached storage.

    Categories:

    - front-bay
    - internal-nvme
    - boot-media
    - unassigned
    """

    def __init__(
        self,
        enclosure: EnclosureController,
        topology: TopologyResolver,
        *,
        block_root: str | Path = DEFAULT_BLOCK_ROOT,
        config: Mapping | None = None,
    ) -> None:
        self.enclosure = enclosure
        self.topology = topology
        self.block_root = Path(block_root)
        self.config = dict(config or {})

    def drives(self) -> list[Drive]:
        """Return all discovered whole-disk block devices."""

        try:
            entries = list(self.block_root.iterdir())
        except (FileNotFoundError, PermissionError, NotADirectoryError, OSError):
            return []

        drives: list[Drive] = []

        for path in sorted(entries, key=lambda item: item.name):
            if not self._is_whole_disk(path):
                continue

            drives.append(self._read_drive(path))

        return drives

    def front_bays(self) -> list[FrontBay]:
        """Return the resolved physical front-bay topology."""

        drives = self.drives()

        return self.topology.resolve_front_bays(
            self.enclosure.slots(),
            drives,
        )

    def devices(self) -> list[StorageDevice]:
        """Return every drive classified into the logical topology."""

        drives = self.drives()
        drive_by_device = {
            drive.device: drive
            for drive in drives
        }

        front_bays = self.topology.resolve_front_bays(
            self.enclosure.slots(),
            drives,
        )

        inventory: list[StorageDevice] = []
        assigned: set[str] = set()

        for bay in front_bays:
            if not bay.installed or not bay.device:
                continue

            drive = drive_by_device.get(bay.device)

            if drive is None:
                continue

            assigned.add(drive.device)

            inventory.append(
                StorageDevice(
                    drive=drive,
                    category="front-bay",
                    label=bay.display_name,
                    physical_bay=bay.physical_bay,
                    kernel_slot=bay.kernel_slot,
                    enclosure=bay.enclosure,
                    mapping_source=bay.mapping_source,
                )
            )

        nvme_index = 0
        boot_index = 0
        unassigned_index = 0

        for drive in drives:
            if drive.device in assigned:
                continue

            category = self._classify_unassigned_drive(drive)

            if category == "internal-nvme":
                nvme_index += 1
                label = f"Internal NVMe {nvme_index}"
            elif category == "boot-media":
                boot_index += 1
                label = (
                    "Boot Media"
                    if boot_index == 1
                    else f"Boot Media {boot_index}"
                )
            else:
                unassigned_index += 1
                label = (
                    "Unassigned Storage"
                    if unassigned_index == 1
                    else f"Unassigned Storage {unassigned_index}"
                )

            inventory.append(
                StorageDevice(
                    drive=drive,
                    category=category,
                    label=label,
                )
            )

        return sorted(
            inventory,
            key=self._inventory_sort_key,
        )

    def by_category(self, category: str) -> list[StorageDevice]:
        """Return inventory entries belonging to one category."""

        return [
            entry
            for entry in self.devices()
            if entry.category == category
        ]

    def find_device(self, device: str) -> StorageDevice | None:
        """Find an inventory entry by `sda` or `/dev/sda`."""

        normalized = Path(device).name

        for entry in self.devices():
            if entry.device == normalized:
                return entry

        return None

    @staticmethod
    def _is_whole_disk(path: Path) -> bool:
        name = path.name

        if (path / "partition").exists():
            return False

        if name.startswith(("loop", "ram", "zram", "dm-")):
            return False

        return name.startswith(("sd", "hd", "vd", "xvd", "nvme", "mmcblk"))

    @staticmethod
    def _read_drive(path: Path) -> Drive:
        device_path = path / "device"

        model = (
            _read_text(device_path / "model")
            or _read_text(device_path / "name")
        )

        serial = (
            _read_text(device_path / "serial")
            or _read_vpd_serial(device_path / "vpd_pg80")
            or _read_ancestor_serial(device_path)
        )

        removable = _read_text(path / "removable").lower() in {
            "1",
            "yes",
            "true",
        }

        sectors = _read_int(path / "size")
        size_bytes = sectors * 512

        transport = StorageInventory._detect_transport(
            path=path,
            model=model,
            removable=removable,
        )

        return Drive(
            device=path.name,
            model=model,
            serial=serial,
            transport=transport,
            removable=removable,
            size_bytes=size_bytes,
            sysfs_path=path,
        )

    @staticmethod
    def _detect_transport(
        *,
        path: Path,
        model: str,
        removable: bool,
    ) -> str:
        explicit = _read_text(path / "device" / "transport").lower()

        if explicit:
            return explicit

        name = path.name.lower()
        model_lower = model.lower()

        if name.startswith("nvme"):
            return "nvme"

        if "usb" in model_lower or removable:
            return "usb"

        try:
            resolved = str(path.resolve()).lower()
        except OSError:
            resolved = str(path).lower()

        if "/usb" in resolved:
            return "usb"

        if "/ata" in resolved:
            return "sata"

        return "unknown"

    @staticmethod
    def _classify_unassigned_drive(drive: Drive) -> str:
        if drive.transport == "nvme" or drive.device.startswith("nvme"):
            return "internal-nvme"

        if drive.transport == "usb":
            return "boot-media"

        return "unassigned"

    @staticmethod
    def _inventory_sort_key(entry: StorageDevice) -> tuple:
        category_order = {
            "front-bay": 0,
            "internal-nvme": 1,
            "boot-media": 2,
            "unassigned": 3,
        }

        return (
            category_order.get(entry.category, 99),
            entry.physical_bay or 0,
            entry.device,
        )


__all__ = [
    "DEFAULT_BLOCK_ROOT",
    "Drive",
    "StorageDevice",
    "StorageInventory",
]
