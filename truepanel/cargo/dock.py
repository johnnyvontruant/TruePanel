"""Loadmaster cartridge dock: detect, identify, mount, and release USB cartridges.

The dock answers one question for the Loadmaster controller: *is exactly one
registered cartridge physically attached over USB, and where is it mounted?*

Identity is fail-closed:

* a block device is only a cartridge candidate when its filesystem UUID matches
  a registry entry **and** its parent disk is attached over USB;
* when the registry pins a ``device_serial``, the disk serial must match;
* two docked cartridges at once, an unsupported filesystem, or a cartridge
  already mounted somewhere Loadmaster does not own is a HOLD, never a guess.

Mount authority is deliberately narrow. Cartridges are mounted read-only under
``mount_root/<cartridge-id>`` for planning, remounted read-write only for an
executor run that a physical Copy press has confirmed, and unmounted (after a
``sync``) as soon as that run ends. The dock never formats, repairs, deletes,
or writes media itself.

All external commands go through an injectable ``runner`` so tests and dry
runs never touch real block devices.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cartridges import CartridgeDefinition

DEFAULT_MOUNT_ROOT = Path("/mnt/loadmaster")

# lsblk FSTYPE -> mount -t type. NTFS is mounted with the in-kernel ntfs3
# driver that TrueNAS SCALE ships; ntfs-3g is not assumed.
DEFAULT_FILESYSTEM_TYPES: dict[str, str] = {
    "exfat": "exfat",
    "vfat": "vfat",
    "ntfs": "ntfs3",
    "ext4": "ext4",
    "xfs": "xfs",
    "btrfs": "btrfs",
}

MOUNT_OPTIONS_RO = "ro,nosuid,nodev,noexec,noatime"
MOUNT_OPTIONS_RW = "rw,nosuid,nodev,noexec,noatime"

LSBLK_COLUMNS = (
    "NAME,PATH,TYPE,UUID,FSTYPE,LABEL,SERIAL,TRAN,RM,HOTPLUG,MOUNTPOINTS,SIZE"
)

Runner = Callable[[Sequence[str]], str]


class LoadmasterDockError(RuntimeError):
    """Fail-closed dock error."""


def subprocess_runner(argv: Sequence[str]) -> str:
    """Run one command without a shell and return stdout."""

    try:
        completed = subprocess.run(
            list(argv),
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError as error:
        raise LoadmasterDockError(f"command unavailable: {argv[0]}") from error
    except subprocess.TimeoutExpired as error:
        raise LoadmasterDockError(f"command timed out: {' '.join(argv)}") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip()
        raise LoadmasterDockError(
            f"command failed ({error.returncode}): {' '.join(argv)}: {detail}"
        ) from error

    return completed.stdout


@dataclass(frozen=True)
class BlockDevice:
    """One filesystem-bearing block device as reported by lsblk."""

    path: str
    uuid: str
    fstype: str
    label: str
    serial: str
    transport: str
    removable: bool
    mountpoints: tuple[str, ...]
    size_bytes: int


@dataclass(frozen=True)
class DockedCartridge:
    """A registry cartridge positively identified on one USB block device."""

    cartridge: CartridgeDefinition
    device: BlockDevice
    identity_verified: bool
    identity_reason: str

    @property
    def key(self) -> tuple[str, str, str]:
        """Stable identity for one physical insertion."""

        return (
            self.cartridge.cartridge_id,
            self.device.path,
            self.device.uuid.casefold(),
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "cartridge_id": self.cartridge.cartridge_id,
            "label": self.cartridge.label,
            "role": self.cartridge.role,
            "device": self.device.path,
            "fstype": self.device.fstype,
            "filesystem_label": self.device.label,
            "size_bytes": self.device.size_bytes,
            "identity_verified": self.identity_verified,
            "identity_reason": self.identity_reason,
        }


@dataclass(frozen=True)
class DockScan:
    """Result of one dock scan."""

    docked: tuple[DockedCartridge, ...]
    unknown_usb_filesystems: int

    @property
    def state(self) -> str:
        if not self.docked:
            return "EMPTY"
        if len(self.docked) > 1:
            return "MULTIPLE"
        return "DOCKED"


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _mountpoints(node: dict[str, Any]) -> tuple[str, ...]:
    raw = node.get("mountpoints")
    if raw is None:
        raw = [node.get("mountpoint")]
    if not isinstance(raw, list):
        raw = [raw]
    return tuple(str(item) for item in raw if item)


def parse_lsblk(payload: str) -> list[BlockDevice]:
    """Flatten ``lsblk -J`` output, inheriting disk serial/transport."""

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as error:
        raise LoadmasterDockError(f"lsblk output is not JSON: {error}") from error

    devices = data.get("blockdevices") if isinstance(data, dict) else None
    if not isinstance(devices, list):
        raise LoadmasterDockError("lsblk output has no blockdevices list")

    result: list[BlockDevice] = []

    def walk(node: Any, inherited: dict[str, Any]) -> None:
        if not isinstance(node, dict):
            return

        serial = str(node.get("serial") or "").strip() or inherited.get("serial", "")
        transport = str(node.get("tran") or "").strip().lower() or inherited.get(
            "tran", ""
        )
        removable = (
            _truthy(node.get("rm"))
            or _truthy(node.get("hotplug"))
            or bool(inherited.get("removable"))
        )

        uuid = str(node.get("uuid") or "").strip()
        fstype = str(node.get("fstype") or "").strip().lower()
        path = str(node.get("path") or "").strip() or (
            f"/dev/{node.get('name')}" if node.get("name") else ""
        )

        if uuid and fstype and path:
            result.append(
                BlockDevice(
                    path=path,
                    uuid=uuid,
                    fstype=fstype,
                    label=str(node.get("label") or "").strip(),
                    serial=serial,
                    transport=transport,
                    removable=removable,
                    mountpoints=_mountpoints(node),
                    size_bytes=_int(node.get("size")),
                )
            )

        for child in node.get("children") or []:
            walk(
                child,
                {"serial": serial, "tran": transport, "removable": removable},
            )

    for device in devices:
        walk(device, {})

    return result


class CartridgeDock:
    """Detect registered USB cartridges and own their Loadmaster mounts."""

    def __init__(
        self,
        *,
        cartridges: Sequence[CartridgeDefinition],
        mount_root: Path = DEFAULT_MOUNT_ROOT,
        runner: Runner = subprocess_runner,
        filesystem_types: dict[str, str] | None = None,
        require_usb_transport: bool = True,
        mountinfo_reader: Callable[[], str] | None = None,
    ) -> None:
        if not mount_root.is_absolute():
            raise LoadmasterDockError("dock mount_root must be absolute")

        self.cartridges = tuple(cartridges)
        self.mount_root = mount_root
        self.runner = runner
        self.filesystem_types = dict(filesystem_types or DEFAULT_FILESYSTEM_TYPES)
        self.require_usb_transport = bool(require_usb_transport)
        self._mountinfo_reader = mountinfo_reader or _read_proc_mountinfo
        self._by_uuid = {
            cartridge.uuid.casefold(): cartridge for cartridge in self.cartridges
        }

    # ------------------------------------------------------------------ scan

    def scan(self) -> DockScan:
        devices = parse_lsblk(self.runner(["lsblk", "-J", "-b", "-o", LSBLK_COLUMNS]))

        docked: list[DockedCartridge] = []
        unknown = 0

        for device in devices:
            usb = device.transport == "usb"
            cartridge = self._by_uuid.get(device.uuid.casefold())

            if cartridge is None:
                if usb:
                    unknown += 1
                continue

            if self.require_usb_transport and not usb:
                # A registered UUID on a non-USB disk is never a cartridge.
                continue

            docked.append(self._identify(cartridge, device))

        return DockScan(docked=tuple(docked), unknown_usb_filesystems=unknown)

    def _identify(
        self,
        cartridge: CartridgeDefinition,
        device: BlockDevice,
    ) -> DockedCartridge:
        if device.fstype not in self.filesystem_types:
            return DockedCartridge(
                cartridge, device, False, f"UNSUPPORTED_FILESYSTEM:{device.fstype}"
            )

        if not device.serial:
            return DockedCartridge(
                cartridge, device, False, "DEVICE_SERIAL_UNAVAILABLE"
            )

        if cartridge.device_serial and (
            cartridge.device_serial.casefold() != device.serial.casefold()
        ):
            return DockedCartridge(cartridge, device, False, "DEVICE_SERIAL_MISMATCH")

        reason = "UUID_AND_SERIAL" if cartridge.device_serial else "UUID_ONLY"
        return DockedCartridge(cartridge, device, True, reason)

    # ----------------------------------------------------------------- mounts

    def mountpoint_for(self, docked: DockedCartridge) -> Path:
        return self.mount_root / docked.cartridge.cartridge_id

    def _mounts(self) -> dict[str, tuple[str, str]]:
        """Map mount target -> (source, options) from /proc/self/mountinfo."""

        result: dict[str, tuple[str, str]] = {}
        for line in self._mountinfo_reader().splitlines():
            left, _, right = line.partition(" - ")
            fields = left.split()
            tail = right.split()
            if len(fields) < 6 or len(tail) < 2:
                continue
            target = _unescape_mount(fields[4])
            options = fields[5]
            source = _unescape_mount(tail[1])
            result[target] = (source, options)
        return result

    def mount_state(self, docked: DockedCartridge) -> str:
        """Return UNMOUNTED, MOUNTED_RO, MOUNTED_RW, or FOREIGN."""

        mountpoint = str(self.mountpoint_for(docked))
        mounts = self._mounts()

        ours = mounts.get(mountpoint)
        if ours is not None:
            source, options = ours
            if os.path.realpath(source) != os.path.realpath(docked.device.path):
                return "FOREIGN"
            return "MOUNTED_RW" if "rw" in options.split(",") else "MOUNTED_RO"

        for source, _options in mounts.values():
            if os.path.realpath(source) == os.path.realpath(docked.device.path):
                return "FOREIGN"

        if docked.device.mountpoints:
            return "FOREIGN"

        return "UNMOUNTED"

    def _prepare_mountpoint(self, mountpoint: Path) -> None:
        try:
            info = self.mount_root.lstat()
        except FileNotFoundError:
            self.mount_root.mkdir(mode=0o755, parents=True)
            info = self.mount_root.lstat()

        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise LoadmasterDockError(
                f"dock mount_root is not a real directory: {self.mount_root}"
            )

        try:
            info = mountpoint.lstat()
        except FileNotFoundError:
            mountpoint.mkdir(mode=0o755)
            return

        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise LoadmasterDockError(
                f"dock mountpoint is not a real directory: {mountpoint}"
            )

        if any(mountpoint.iterdir()):
            raise LoadmasterDockError(
                f"dock mountpoint is not empty while unmounted: {mountpoint}"
            )

    def mount_read_only(self, docked: DockedCartridge) -> Path:
        """Mount (or confirm) the cartridge read-only for planning."""

        if not docked.identity_verified:
            raise LoadmasterDockError(
                f"cartridge identity not verified: {docked.identity_reason}"
            )

        mountpoint = self.mountpoint_for(docked)
        state = self.mount_state(docked)

        if state == "FOREIGN":
            raise LoadmasterDockError(
                "cartridge is mounted somewhere Loadmaster does not own; "
                "unmount it first"
            )

        if state == "MOUNTED_RO":
            return mountpoint

        if state == "MOUNTED_RW":
            self._remount(mountpoint, MOUNT_OPTIONS_RO)
            return mountpoint

        self._prepare_mountpoint(mountpoint)
        self.runner(
            [
                "mount",
                "-t",
                self.filesystem_types[docked.device.fstype],
                "-o",
                MOUNT_OPTIONS_RO,
                docked.device.path,
                str(mountpoint),
            ]
        )
        return mountpoint

    def remount_read_write(self, docked: DockedCartridge) -> Path:
        """Grant write access for one confirmed executor run."""

        mountpoint = self.mountpoint_for(docked)
        state = self.mount_state(docked)

        if state not in {"MOUNTED_RO", "MOUNTED_RW"}:
            raise LoadmasterDockError(
                f"cartridge is not mounted by Loadmaster (state {state})"
            )

        if state == "MOUNTED_RO":
            self._remount(mountpoint, MOUNT_OPTIONS_RW)

        return mountpoint

    def _remount(self, mountpoint: Path, options: str) -> None:
        self.runner(["mount", "-o", f"remount,{options}", str(mountpoint)])

    def release(self, docked: DockedCartridge, *, lazy: bool = False) -> None:
        """Flush and unmount a Loadmaster-owned cartridge mount."""

        mountpoint = self.mountpoint_for(docked)
        state = self.mount_state(docked)

        if state in {"UNMOUNTED", "FOREIGN"}:
            return

        try:
            self.runner(["sync"])
        except LoadmasterDockError:
            if not lazy:
                raise

        argv = (
            ["umount", "-l", str(mountpoint)] if lazy else ["umount", str(mountpoint)]
        )
        self.runner(argv)

    def release_orphan(self, cartridge_id: str) -> None:
        """Lazily detach a Loadmaster mount whose device disappeared."""

        mountpoint = str(self.mount_root / cartridge_id)
        if mountpoint in self._mounts():
            self.runner(["umount", "-l", mountpoint])


def _unescape_mount(value: str) -> str:
    return (
        value.replace("\\040", " ")
        .replace("\\011", "\t")
        .replace("\\012", "\n")
        .replace("\\134", "\\")
    )


def _read_proc_mountinfo() -> str:
    return Path("/proc/self/mountinfo").read_text(encoding="utf-8")


__all__ = [
    "BlockDevice",
    "CartridgeDock",
    "DEFAULT_FILESYSTEM_TYPES",
    "DEFAULT_MOUNT_ROOT",
    "DockScan",
    "DockedCartridge",
    "LoadmasterDockError",
    "MOUNT_OPTIONS_RO",
    "MOUNT_OPTIONS_RW",
    "parse_lsblk",
    "subprocess_runner",
]
