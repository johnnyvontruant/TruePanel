"""Exact-device TV N-Z independent read-only restoration guard.

Distinct from the synthetic spare guard. This module NEVER mounts writable,
grants GPIO approval or copies data. All RO recovery actions are bound to one
confirmed exFAT partition, UUID, serial and absolute mountpoint.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .backup_executor import BackupExecutionError

TV_NZ_SERIAL = "2532EA8D3DC7"
TV_NZ_UUID = "6988-53EB"
TV_NZ_BY_ID = "/dev/disk/by-id/usb-Micron_CT8000X10SSD9_2532EA8D3DC7-0:0-part2"
TV_NZ_MOUNT = Path("/mnt/loadmaster-tv-nz-ro")
TV_NZ_LIBRARY = Path("/mnt/HDDs/Shows/TV N-Z")
TV_NZ_CARTRIDGE_ROOT = TV_NZ_MOUNT / "TV N-Z"
TV_NZ_TEST_RELATIVE = "Nobody Wants This (2024)/3x01 - It's Perfect.mkv"
MAX_TV_NZ_LEASE_SECONDS = 180


@dataclass(frozen=True)
class TvNzPin:
    mount: Path = TV_NZ_MOUNT
    by_id: str = TV_NZ_BY_ID
    uuid: str = TV_NZ_UUID
    serial: str = TV_NZ_SERIAL


def _pin(pin: TvNzPin) -> None:
    if (type(pin) is not TvNzPin or
            (pin.mount, pin.by_id, pin.uuid, pin.serial) !=
            (TV_NZ_MOUNT, TV_NZ_BY_ID, TV_NZ_UUID, TV_NZ_SERIAL)):
        raise BackupExecutionError("TV N-Z pin identity is not exact")
    if pin.mount.is_symlink():
        raise BackupExecutionError("symlinked TV N-Z mount is forbidden")


def _call(argv: list[str]) -> str:
    return subprocess.check_output(argv, text=True, timeout=10).strip()


def mount_mode(pin: TvNzPin = TvNzPin(), *,
               command: Callable[[list[str]], str] = _call,
               realpath: Callable[[str], str] = os.path.realpath) -> str:
    """Inspect RO/RW mode of ONLY the physical TV N-Z cartridge."""
    _pin(pin)
    try:
        row = command([
            "findmnt", "-n", "-M", str(pin.mount),
            "-o", "SOURCE,TARGET,FSTYPE,OPTIONS", "--raw"
        ]).strip().split(None, 3)
        if len(row) != 4:
            raise BackupExecutionError("TV N-Z mount not uniquely identified")
        source, target, filesystem, options = row
        if (target != str(pin.mount) or filesystem.lower() != "exfat"
                or not source.startswith("/dev/")):
            raise BackupExecutionError("unexpected TV N-Z mount")
        observed_uuid = command(["blkid", "-s", "UUID", "-o", "value", source]).strip()
        observed_fs = command(["blkid", "-s", "TYPE", "-o", "value", source]).strip()
        mounted = realpath(source)
        pinned = realpath(pin.by_id)
        if (observed_uuid != pin.uuid or observed_fs.lower() != "exfat"
                or not mounted.startswith("/dev/")
                or mounted != pinned
                or not re.search("_" + re.escape(pin.serial) + r"-0:0-part2$", pin.by_id)):
            raise BackupExecutionError("TV N-Z physical identity changed")
        flags = set(options.split(","))
        if ("ro" in flags) == ("rw" in flags):
            raise BackupExecutionError("ambiguous TV N-Z mount mode")
        return "ro" if "ro" in flags else "rw"
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise BackupExecutionError("TV N-Z mount observation failed") from exc


def restore_ro(pin: TvNzPin = TvNzPin(), *,
               inspect: Callable[[TvNzPin], str] = mount_mode,
               remount_ro: Callable[[Path], None] | None = None) -> str:
    """RO-only recovery; never remount an unrecognized or substituted drive."""
    _pin(pin)
    mode = inspect(pin)
    if mode not in ("ro", "rw"):
        raise BackupExecutionError("TV N-Z mount cannot be qualified")
    if mode == "rw":
        if remount_ro is None:
            def remount_ro(mount: Path) -> None:
                subprocess.run(
                    ["mount", "-o", "remount,ro", str(mount)],
                    check=True, capture_output=True, text=True, timeout=20)
        remount_ro(pin.mount)
    if inspect(pin) != "ro":
        raise BackupExecutionError("CRITICAL: TV N-Z RO restoration unverified")
    return "RESTORED_RO"


def guard_loop(*, pin: TvNzPin, owner_pid: int, owner_ticks: int,
               deadline: float, report: Callable[[str], None],
               inspect: Callable[[TvNzPin], str] = mount_mode,
               owner_alive: Callable[[int, int], bool] | None = None,
               remount_ro: Callable[[Path], None] | None = None,
               now: Callable[[], float] = time.monotonic,
               pause: Callable[[float], None] = time.sleep) -> str:
    """Independent monitor whose only potential mount change is RW -> RO."""
    from .independent_ro_watchdog import _owner_alive
    _pin(pin)
    alive = _owner_alive if owner_alive is None else owner_alive
    if (type(owner_pid) is not int or owner_pid <= 1
            or type(owner_ticks) is not int or owner_ticks < 1
            or not (0 < deadline - now() <= MAX_TV_NZ_LEASE_SECONDS)):
        raise BackupExecutionError("invalid TV N-Z guard lease")
    if inspect(pin) != "ro" or not alive(owner_pid, owner_ticks):
        raise BackupExecutionError("TV N-Z guard must start RO with owner alive")
    report("READY")
    last = now()
    while True:
        mode = inspect(pin)
        if mode not in ("ro", "rw"):
            raise BackupExecutionError("TV N-Z mount identity no longer trusted")
        if now() >= deadline or not alive(owner_pid, owner_ticks):
            result = restore_ro(pin, inspect=inspect, remount_ro=remount_ro)
            report(result)
            return result
        if now() - last >= 1.0:
            report("READY")
            last = now()
        pause(0.1)


def preflight(pin: TvNzPin = TvNzPin()) -> dict:
    """Device-bound survey; no watchdog started and no mount changes."""
    if mount_mode(pin) != "ro":
        raise BackupExecutionError("TV N-Z must be RO for preflight")
    return {
        "state": "TV_NZ_RO_GUARD_PREFLIGHT_PASS",
        "serial": pin.serial,
        "uuid": pin.uuid,
        "mount": str(pin.mount),
        "mount_mode": "ro",
        "usb_written": False,
        "gpio_armed": False,
        "guard_running": False,
    }
