"""Find Loadmaster drives on USB and own their mounts.

A USB filesystem is a Loadmaster drive when its **label** matches a configured
drive name (case-insensitive). Loadmaster mounts it under
``mount_root/<drive-key>`` read-only for planning, remounts it read-write only
for a run, and syncs and unmounts it afterwards. A drive already mounted
somewhere else is left alone. TrueNAS does not auto-mount USB disks, so this
is normally the only mount.

Commands run through an injectable ``runner`` so tests never touch devices.
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

from .config import Drive

# lsblk FSTYPE -> mount -t. NTFS uses the in-kernel ntfs3 driver TrueNAS ships.
MOUNT_TYPES = {
    "exfat": "exfat",
    "vfat": "vfat",
    "ntfs": "ntfs3",
    "ext4": "ext4",
    "xfs": "xfs",
    "btrfs": "btrfs",
}
RO = "ro,nosuid,nodev,noexec,noatime"
RW = "rw,nosuid,nodev,noexec,noatime"
LSBLK = [
    "lsblk",
    "-J",
    "-b",
    "-o",
    "PATH,PKNAME,UUID,FSTYPE,LABEL,SERIAL,TRAN,SIZE,MOUNTPOINTS",
]

Runner = Callable[[Sequence[str]], str]


class DockError(RuntimeError):
    pass


def run_command(argv: Sequence[str]) -> str:
    try:
        done = subprocess.run(
            list(argv), check=True, capture_output=True, text=True, timeout=120
        )
    except FileNotFoundError as error:
        raise DockError(f"{argv[0]} is not installed") from error
    except subprocess.TimeoutExpired as error:
        raise DockError(f"timed out: {' '.join(argv)}") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip()
        raise DockError(f"{' '.join(argv[:2])} failed: {detail}") from error
    return done.stdout


@dataclass(frozen=True)
class Device:
    path: str
    uuid: str
    fstype: str
    label: str
    serial: str
    usb: bool
    size: int
    mountpoints: tuple[str, ...]


@dataclass(frozen=True)
class Docked:
    drive: Drive
    device: Device

    @property
    def insertion(self) -> tuple[str, str, str]:
        """Identity of one physical insertion."""

        return (self.drive.key, self.device.path, self.device.uuid)

    def public(self) -> dict[str, Any]:
        return {
            "name": self.drive.name,
            "device": self.device.path,
            "uuid": self.device.uuid,
            "serial": self.device.serial,
            "fstype": self.device.fstype,
            "size": self.device.size,
        }


def parse_lsblk(text: str) -> list[Device]:
    try:
        roots = json.loads(text)["blockdevices"]
    except (ValueError, KeyError, TypeError) as error:
        raise DockError("could not read lsblk output") from error

    devices: list[Device] = []

    def walk(node: dict[str, Any], serial: str, tran: str) -> None:
        serial = str(node.get("serial") or "").strip() or serial
        # An lsblk child may report a different transport for its partition.\n        # Physical USB ancestry takes precedence: a partition cannot cease\n        # being USB-attached merely because its own TRAN differs.\n        tran = "usb" if tran == "usb" else (str(node.get("tran") or "").strip().lower() or tran)
        uuid = str(node.get("uuid") or "").strip()
        fstype = str(node.get("fstype") or "").strip().lower()
        if uuid and fstype and node.get("path"):
            points = node.get("mountpoints") or []
            devices.append(
                Device(
                    path=str(node["path"]),
                    uuid=uuid,
                    fstype=fstype,
                    label=str(node.get("label") or "").strip(),
                    serial=serial,
                    usb=tran == "usb",
                    size=int(node.get("size") or 0),
                    mountpoints=tuple(str(p) for p in points if p),
                )
            )
        for child in node.get("children") or []:
            walk(child, serial, tran)

    # Flat lsblk output on TrueNAS requires resolving parent disks by PKNAME.
    by_path = {}
    def index(node):
        if node.get("path"):
            by_path[node["path"]] = node
        for child in node.get("children") or []:
            index(child)

    for root in roots or []:
        index(root)

    def ancestry(node):
        serial, transport = "", ""
        seen = set()
        while node:
            path = node.get("path")
            if path in seen:
                break
            seen.add(path)
            serial = serial or str(node.get("serial") or "").strip()
            child_transport = str(node.get("tran") or "").strip().lower()
            if child_transport == "usb":
                transport = "usb"
            elif not transport:
                transport = child_transport
            parent = str(node.get("pkname") or "").strip()
            if not parent:
                break
            node = by_path.get(parent if parent.startswith("/dev/") else "/dev/" + parent)
        return serial, transport

    for root in roots or []:
        serial, transport = ancestry(root)
        walk(root, serial, transport)
    return devices


def _unescape(value: str) -> str:
    return (
        value.replace("\\040", " ")
        .replace("\\011", "\t")
        .replace("\\012", "\n")
        .replace("\\134", "\\")
    )


def _read_mountinfo() -> str:
    return Path("/proc/self/mountinfo").read_text(encoding="utf-8")


class Dock:
    def __init__(
        self,
        drives: Sequence[Drive],
        mount_root: Path,
        *,
        runner: Runner = run_command,
        mountinfo: Callable[[], str] = _read_mountinfo,
    ) -> None:
        self.drives = {drive.name.casefold(): drive for drive in drives}
        self.mount_root = mount_root
        self.runner = runner
        self.mountinfo = mountinfo

    def scan(self) -> list[Docked]:
        """Every configured drive currently attached over USB."""

        found = []
        for device in parse_lsblk(self.runner(LSBLK)):
            drive = self.drives.get(device.label.casefold())
            if drive is not None and device.usb:
                found.append(Docked(drive, device))
        return found

    # ------------------------------------------------------------- mounts

    def mountpoint(self, docked: Docked) -> Path:
        return self.mount_root / docked.drive.key

    def _mounts(self) -> dict[str, tuple[str, str]]:
        result = {}
        for line in self.mountinfo().splitlines():
            left, _, right = line.partition(" - ")
            fields, tail = left.split(), right.split()
            if len(fields) >= 6 and len(tail) >= 2:
                result[_unescape(fields[4])] = (_unescape(tail[1]), fields[5])
        return result

    def mount_state(self, docked: Docked) -> str:
        """UNMOUNTED, RO, RW, or ELSEWHERE (mounted by something else)."""

        device = os.path.realpath(docked.device.path)
        mounts = self._mounts()
        ours = mounts.get(str(self.mountpoint(docked)))
        if ours is not None:
            source, options = ours
            if os.path.realpath(source) != device:
                return "ELSEWHERE"
            return "RW" if "rw" in options.split(",") else "RO"
        if docked.device.mountpoints or any(
            os.path.realpath(source) == device for source, _ in mounts.values()
        ):
            return "ELSEWHERE"
        return "UNMOUNTED"

    def mount_ro(self, docked: Docked) -> Path:
        point = self.mountpoint(docked)
        state = self.mount_state(docked)
        if state == "ELSEWHERE":
            raise DockError("the drive is already mounted elsewhere; unmount it first")
        if state == "RO":
            return point
        if state == "RW":
            self.runner(["mount", "-o", f"remount,{RO}", str(point)])
            return point

        mount_type = MOUNT_TYPES.get(docked.device.fstype)
        if mount_type is None:
            raise DockError(f"unsupported filesystem {docked.device.fstype}")
        self.mount_root.mkdir(parents=True, exist_ok=True)
        try:
            info = point.lstat()
        except FileNotFoundError:
            point.mkdir()
        else:
            if not stat.S_ISDIR(info.st_mode) or any(point.iterdir()):
                raise DockError(f"mountpoint {point} is not an empty folder")
        self.runner(
            ["mount", "-t", mount_type, "-o", RO, docked.device.path, str(point)]
        )
        return point

    def mount_rw(self, docked: Docked) -> Path:
        point = self.mountpoint(docked)
        state = self.mount_state(docked)
        if state == "RO":
            self.runner(["mount", "-o", f"remount,{RW}", str(point)])
        elif state != "RW":
            raise DockError(f"drive is not mounted by Loadmaster ({state})")
        return point

    def release(self, docked: Docked) -> None:
        """Flush and unmount. Safe to call when already unmounted."""

        if self.mount_state(docked) in {"RO", "RW"}:
            self.runner(["sync"])
            self.runner(["umount", str(self.mountpoint(docked))])

    def release_vanished(self, key: str) -> None:
        """Lazily detach our mount for a drive that was unplugged."""

        point = str(self.mount_root / key)
        if point in self._mounts():
            self.runner(["umount", "-l", point])


__all__ = ["Device", "Dock", "DockError", "Docked", "parse_lsblk", "run_command"]
