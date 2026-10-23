"""Fail-closed *candidate* independent RO restoration guard for the spare USB.

Never remounts RW, never acts on media other than the exact known spare.
Not connected to any production service or physical actuator. For use by a
separate systemd service, not a thread of the transfer runner. Live activation
requires systemd service/kill-path qualification on BattleStation.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .backup_executor import BackupExecutionError

SPARE_SERIAL = '2532EA8D421A'
SPARE_UUID = '6ADA-80D5'
SPARE_BY_ID = '/dev/disk/by-id/usb-Micron_CT8000X10SSD9_2532EA8D421A-0:0-part2'
SPARE_MOUNT = Path('/mnt/loadmaster-spare-ro')
UNIT_PREFIX = 'loadmaster-ro-guard-'
MAX_LEASE_SECONDS = 180
MAX_STATUS_AGE_SECONDS = 3.0


@dataclass(frozen=True)
class SparePin:
    mount: Path = SPARE_MOUNT
    by_id: str = SPARE_BY_ID
    uuid: str = SPARE_UUID
    serial: str = SPARE_SERIAL


def _pinned(pin: SparePin) -> None:
    if type(pin) is not SparePin or (pin.mount, pin.by_id, pin.uuid, pin.serial) != (
            SPARE_MOUNT, SPARE_BY_ID, SPARE_UUID, SPARE_SERIAL):
        raise BackupExecutionError('RO guardian only supports exact spare cartridge')
    if pin.mount.is_symlink():
        raise BackupExecutionError('symlinked spare mount rejected')


def _command(argv: list[str]) -> str:
    return subprocess.check_output(argv, text=True, timeout=8).strip()


def mount_mode(pin: SparePin, *, command: Callable[[list[str]], str] = _command,
               realpath: Callable[[str], str] = os.path.realpath) -> str:
    """Return ro/rw only for exact mounted exFAT partition and pinned by-id link.

    Read-only commands. Never infer a mount from /dev/sda naming alone.
    """
    _pinned(pin)
    try:
        tokens = command(['findmnt', '-n', '-M', str(pin.mount), '-o',
                          'SOURCE,TARGET,FSTYPE,OPTIONS', '--raw']).strip().split(None, 3)
        if len(tokens) != 4:
            raise BackupExecutionError('missing/ambiguous exact mount')
        source, target, filesystem, option_string = tokens
        if (target != str(pin.mount) or filesystem.lower() != 'exfat'
                or not source.startswith('/dev/')):
            raise BackupExecutionError('unexpected exFAT mount source')
        if command(['blkid', '-s', 'UUID', '-o', 'value', source]).strip() != pin.uuid:
            raise BackupExecutionError('mounted UUID changed')
        if command(['blkid', '-s', 'TYPE', '-o', 'value', source]).strip().lower() != 'exfat':
            raise BackupExecutionError('mounted filesystem changed')
        if realpath(source) != realpath(pin.by_id) or not realpath(pin.by_id).startswith('/dev/'):
            raise BackupExecutionError('mounted partition is not pinned USB device')
        # The by-id name must contain exactly the full known serial.
        if not re.search(r'_' + re.escape(pin.serial) + r'-0:0-part2$', pin.by_id):
            raise BackupExecutionError('cartridge serial mismatch')
        opts = set(option_string.split(','))
        if ('ro' in opts) == ('rw' in opts):
            raise BackupExecutionError('ambiguous read-only/writable mount mode')
        return 'ro' if 'ro' in opts else 'rw'
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise BackupExecutionError('spare mount identity inspection failed') from error


def same_host_mount_namespace(pid: int) -> bool:
    """Require the watchdog to share PID 1's host mount namespace.

    systemd's ProtectSystem= and PrivateMounts= create service-specific mount
    namespaces. A successful remount inside one is NOT proof the host is RO.
    Refuse unreadable, missing, reused or bogus PIDs instead of trusting status.
    """
    if type(pid) is not int or pid < 2:
        return False
    try:
        return (os.readlink(f'/proc/{pid}/ns/mnt')
                == os.readlink('/proc/1/ns/mnt'))
    except (OSError, ValueError):
        return False


def _owner_alive(pid: int, expected_start_ticks: int) -> bool:
    """PID reuse protected through /proc/<pid>/stat start-time field."""
    if type(pid) is not int or pid < 2 or type(expected_start_ticks) is not int or expected_start_ticks < 1:
        return False
    try:
        stat_text = Path(f'/proc/{pid}/stat').read_text()
        tail = stat_text.rsplit(') ', 1)[1].split()
        return tail[0] != 'Z' and int(tail[19]) == expected_start_ticks
    except (OSError, ValueError, IndexError):
        return False


def owner_start_ticks(pid: int) -> int:
    stat_text = Path(f'/proc/{pid}/stat').read_text()
    ticks = int(stat_text.rsplit(') ', 1)[1].split()[19])
    if ticks < 1:
        raise BackupExecutionError('invalid owner process start time')
    return ticks


def _status_file(path: Path) -> None:
    if not path.is_absolute() or not path.is_relative_to(Path('/mnt/SSDs/')):
        raise BackupExecutionError('guard status must reside on private SSD host storage')
    if path.is_symlink() or path.parent.is_symlink() or not path.parent.is_dir():
        raise BackupExecutionError('guard status directory invalid')
    info = path.parent.stat()
    if info.st_uid != 0 or info.st_mode & 0o077:
        raise BackupExecutionError('guard status directory must be root-owned and owner-only')


def write_status(path: Path, payload: dict) -> None:
    """One atomic status replacement; never touches the USB mount."""
    _status_file(path)
    tmp = path.with_name('.' + path.name + '.' + str(os.getpid()) + '.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'w') as stream:
            # Some NAS datasets apply inherited ACL/mode bits even when open()
            # requests 0600. Enforce the security boundary on the real inode
            # before writing or atomically publishing any approval evidence.
            os.fchmod(stream.fileno(), 0o600)
            if os.fstat(stream.fileno()).st_mode & 0o077:
                raise BackupExecutionError('guard status file must be private')
            json.dump(payload, stream, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        dfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        tmp.unlink(missing_ok=True)


def guard_loop(*, pin: SparePin, owner_pid: int, owner_ticks: int,
               deadline: float, report: Callable[[str], None],
               inspect: Callable[[SparePin], str] = mount_mode,
               owner_alive: Callable[[int, int], bool] = _owner_alive,
               remount_ro: Callable[[Path], None] | None = None,
               now: Callable[[], float] = time.monotonic,
               pause: Callable[[float], None] = time.sleep) -> str:
    """Guardian loop, intended in its own systemd service/cgroup.

    Exit successful ONLY if pinned cartridge is independently confirmed RO.
    On owner death or deadline, perform RO-only restoration, never RW.
    Does not kill transfer processes: a mount busy error is a critical failure,
    not a reason to mark restoration successful.
    """
    _pinned(pin)
    if remount_ro is None:
        def remount_ro(path: Path) -> None:
            subprocess.run(['mount', '-o', 'remount,ro', str(path)],
                           capture_output=True, text=True, timeout=15, check=True)
    if (type(owner_pid) is not int or owner_pid <= 1
            or type(owner_ticks) is not int or owner_ticks <= 0
            or not (0 < deadline - now() <= MAX_LEASE_SECONDS)):
        raise BackupExecutionError('invalid watchdog lease')
    if inspect(pin) != 'ro':
        raise BackupExecutionError('guard requires verified initial read-only mount')
    if not owner_alive(owner_pid, owner_ticks):
        raise BackupExecutionError('owner exited before watchdog readiness')
    report('READY')
    last_report = now()
    while True:
        mode = inspect(pin)  # fail closed if device is missing/swapped
        if mode not in ('ro', 'rw'):
            raise BackupExecutionError('unrecognized mount state')
        if now() >= deadline or not owner_alive(owner_pid, owner_ticks):
            if mode == 'rw':
                remount_ro(pin.mount)
            if inspect(pin) != 'ro':
                raise BackupExecutionError('CRITICAL: watchdog could not verify RO restoration')
            report('RESTORED_RO')
            return 'RESTORED_RO'
        if now() - last_report >= 1.0:
            report('READY')
            last_report = now()
        pause(0.1)


def verify_independent_guard(*, path: Path, plan_digest: str, attempt_nonce: str,
                             owner_pid: int, owner_ticks: int, unit: str,
                             monotonic_now: float | None = None,
                             systemd_show: Callable[[str], tuple[str, int]] | None = None,
                             boot_id: str | None = None) -> bool:
    """A status file alone is NEVER evidence of an independent watchdog.

    Require live systemd unit and its actual MainPID equal the fresh guard PID.
    The host must separately verify the pin and monitor service errors.
    """
    try:
        _status_file(path)
        if path.is_symlink() or path.stat().st_mode & 0o077:
            return False
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            return False
        if (not re.fullmatch(r'[a-f0-9]{64}', plan_digest)
                or not re.fullmatch(r'[a-f0-9]{32}', attempt_nonce)
                or not re.fullmatch(r'loadmaster-ro-guard-[a-f0-9]{12}\.service', unit)):
            return False
        if (data.get('state') != 'READY' or data.get('unit') != unit
                or data.get('plan_digest') != plan_digest
                or data.get('attempt_nonce') != attempt_nonce
                or type(data.get('owner_pid')) is not int
                or data['owner_pid'] != owner_pid
                or type(data.get('owner_ticks')) is not int
                or data['owner_ticks'] != owner_ticks
                or type(data.get('guardian_pid')) is not int
                or data['guardian_pid'] < 2
                or data['guardian_pid'] == owner_pid):
            return False
        boot = boot_id if boot_id is not None else Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        if data.get('boot_id') != boot:
            return False
        t = time.monotonic() if monotonic_now is None else monotonic_now
        if (type(data.get('monotonic_at')) not in (int, float)
                or not 0 <= t - data['monotonic_at'] <= MAX_STATUS_AGE_SECONDS):
            return False
        if systemd_show is None:
            def systemd_show(service: str) -> tuple[str, int]:
                fields = _command(['systemctl', 'show', '--property=ActiveState,MainPID', service])
                vals = dict(line.split('=', 1) for line in fields.splitlines() if '=' in line)
                return vals.get('ActiveState', ''), int(vals.get('MainPID', '0'))
        state, main_pid = systemd_show(unit)
        return (state == 'active' and main_pid == data['guardian_pid']
                and same_host_mount_namespace(data['guardian_pid'])
                and _owner_alive(owner_pid, owner_ticks))
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError,
            subprocess.CalledProcessError, subprocess.TimeoutExpired, BackupExecutionError):
        return False


def host_ro_preflight(pin: SparePin = SparePin()) -> dict:
    """Read-only operational check. Does not create a guard or mount RW."""
    mode = mount_mode(pin)
    if mode != 'ro':
        raise BackupExecutionError('spare must be read-only for preflight')
    systemd = _command(['systemctl', '--version']).splitlines()[0]
    _command(['systemd-run', '--version'])
    return {'state': 'READ_ONLY_WATCHDOG_PREFLIGHT', 'serial': pin.serial,
            'uuid': pin.uuid, 'mount': str(pin.mount), 'mount_mode': mode,
            'systemd_version': systemd, 'independent_service_started': False,
            'usb_modified': False}
