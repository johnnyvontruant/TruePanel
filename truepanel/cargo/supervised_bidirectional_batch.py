"""Staged host-owned bidirectional rsync actuator. No CLI or GPIO authority.

The trusted host must supply the already-confirmed direction-bound bridge, a
hardware-attested SupervisedWriteWindow with an independent RO restoration
watchdog, and an authenticated mounted cartridge identity. Not deployed in
TruePanel runtime. No automatic deletions, imports, or overwrites.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Callable

from .backup_executor import BackupExecutionError
from .bidirectional_host_scope import (CargoAction, CargoScope, _stat_and_hash,
                                       inspect_bidirectional, validate_scope)
from .backup_evidence_commit import commit_verified_backup
from .physical_backup_actuator import _writable_identity
from .backup_transaction import _safe_parts
from .os_housekeeping import ignored_os_path


def _no_symlink_chain(path: Path) -> None:
    for p in (path, *path.parents):
        if p.is_symlink():
            raise BackupExecutionError('symlink in physical transfer path')


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _publish_noreplace(staged: Path, destination: Path) -> None:
    """Linux renameat2 no-replace. Fail rather than emulate unsafe os.replace."""
    lib = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(lib, 'renameat2', None)
    if renameat2 is None:
        raise BackupExecutionError('renameat2 no-replace unavailable')
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                          ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    if renameat2(-100, os.fsencode(staged), -100,
                 os.fsencode(destination), 1) != 0:
        error = ctypes.get_errno()
        raise BackupExecutionError('no-replace publish refused: ' + os.strerror(error))
    _fsync_directory(destination.parent)


def _match_file(path: Path, action: CargoAction) -> None:
    actual = _stat_and_hash(path)
    if actual != (action.size_bytes, action.sha256):
        raise BackupExecutionError('source/destination no longer matches exact approval')


def _run_rsync(source: Path, stage: Path) -> None:
    cmd = ['rsync', '-t', '--no-whole-file', '--partial',
           '--partial-dir=.partials', '--no-perms', '--no-owner',
           '--no-group', '--', str(source), str(stage)]
    try:
        subprocess.run(cmd, check=True, timeout=3600, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        # Never publish a partial. Preserve partials for *new* physical approval.
        raise BackupExecutionError('rsync interrupted or failed; staged partial retained') from exc


def transfer_one_approved(*, nas_root: Path, usb_root: Path,
                          action: CargoAction, device_serial: str) -> dict:
    """Pure transport after trusted per-file reattestation and consumed GPIO.

    No mount operations or approval creation. The caller rechecks hardware
    ownership and action identity both before and after this operation.
    """
    _safe_parts(action.relative_path)
    if ignored_os_path(action.relative_path):
        raise BackupExecutionError('OS housekeeping file excluded from physical transfer')
    if action.direction not in ('NAS_TO_USB', 'USB_TO_NAS'):
        raise BackupExecutionError('invalid transfer direction')
    source_root, dest_root = ((nas_root, usb_root) if action.direction == 'NAS_TO_USB'
                              else (usb_root, nas_root))
    source = source_root / action.relative_path
    dest = dest_root / action.relative_path
    for path in (source, dest, source_root, dest_root):
        _no_symlink_chain(path)
    _match_file(source, action)
    if os.path.lexists(dest):
        _match_file(dest, action)
        return {'direction': action.direction, 'relative_path': action.relative_path,
                'state': 'ALREADY_PUBLISHED_VERIFIED', 'new_transfer': False}
    if not re.fullmatch(r'[A-Za-z0-9]{6,64}', device_serial):
        raise BackupExecutionError('invalid serial for staging identity')
    job = hashlib.sha256((device_serial + '\n' + action.direction + '\n' +
                          action.relative_path + '\n' + str(action.size_bytes) +
                          '\n' + action.sha256).encode()).hexdigest()
    stage_parent = dest_root / '.loadmaster-rsync-stage' / job
    _no_symlink_chain(stage_parent)
    stage_parent.mkdir(parents=True, exist_ok=True)
    _no_symlink_chain(stage_parent)
    if not stage_parent.is_dir():
        raise BackupExecutionError('staging directory unavailable')
    staged = stage_parent / 'payload'
    _no_symlink_chain(staged)
    if staged.exists() and not stat.S_ISREG(staged.stat().st_mode):
        raise BackupExecutionError('invalid stage payload')
    _run_rsync(source, staged)
    _match_file(source, action)
    _match_file(staged, action)
    _no_symlink_chain(dest.parent)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _no_symlink_chain(dest.parent)
    if os.path.lexists(dest):
        raise BackupExecutionError('destination appeared before publication')
    fd = os.open(staged, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    _publish_noreplace(staged, dest)
    _match_file(dest, action)
    return {'direction': action.direction, 'relative_path': action.relative_path,
            'state': 'NEW_VERIFIED_COPY', 'new_transfer': True}


def execute_supervised_bidirectional_batch(*, scope: CargoScope, bridge,
        nas_root: Path, usb_root: Path, mount: Path, by_id: str,
        uuid: str, device_serial: str, backup_manifest: Path,
        record_ingest: Callable[[CargoAction, Path, Path], object],
        writable_session, attest_read_only: Callable[[], tuple[str, str, bool]],
        watchdog_verified: Callable[[], bool]) -> dict:
    """Single physical authorization -> bounded two-way batch -> RO -> receipts.

    No direct runtime wiring. The caller must hold exclusive host GPIO/mount
    ownership and an independent write-window watchdog. Approval is consumed
    durably before entering writable context. Fails closed if any condition
    changes; never acts as an unattended retry mechanism.
    """
    validate_scope(scope)
    if (scope.cartridge_uuid != uuid or scope.device_serial != device_serial or
            not all(isinstance(p, Path) and p.is_absolute() for p in
                    (nas_root, usb_root, mount, backup_manifest)) or
            any('..' in p.parts for p in (nas_root, usb_root, mount, backup_manifest)) or
            not re.fullmatch(r'/dev/disk/by-id/[^/]+-part[0-9]+', by_id) or
            not nas_root.is_relative_to(Path('/mnt/SSDs/')) or
            not usb_root.is_relative_to(mount) or usb_root == mount or
            backup_manifest.is_relative_to(mount) or
            not callable(attest_read_only) or not callable(record_ingest) or
            not callable(watchdog_verified) or writable_session is None):
        raise BackupExecutionError('unqualified hardware actuator context')
    for p in (nas_root, usb_root, mount, backup_manifest):
        _no_symlink_chain(p)
    if (not nas_root.is_dir() or not usb_root.is_dir() or
            attest_read_only() != (uuid, device_serial, True)):
        raise BackupExecutionError('mounted cartridge not hardware qualified read-only')
    if not watchdog_verified():
        raise BackupExecutionError('independent read-only restoration watchdog unavailable')
    entries = tuple((a.direction, a.relative_path) for a in scope.actions)
    if inspect_bidirectional(nas_root=nas_root, usb_root=usb_root,
                             entries=entries, recover_verified=True) != scope.actions:
        raise BackupExecutionError('approved mixed batch changed before consumption')
    # Only a host-owned GPIO bridge may return this evidence, and it burns its
    # journal first. Never create our own confirmation or rearm here.
    evidence = bridge.consume_read_only()
    if (type(evidence) is not dict or evidence.get('state') != 'HOST_APPROVAL_EVIDENCE_ONLY'
            or evidence.get('cartridge_id') != scope.cartridge_id or
            evidence.get('plan_digest') != scope.digest or
            evidence.get('executed') is not False or
            evidence.get('physical_execution_enabled') is not False):
        raise BackupExecutionError('host GPIO approval digest mismatch')
    results = []
    with writable_session:
        for action in scope.actions:
            _writable_identity(mount=mount, by_id=by_id, uuid=uuid)
            if not watchdog_verified():
                raise BackupExecutionError('mount restoration watchdog lost')
            if inspect_bidirectional(nas_root=nas_root, usb_root=usb_root,
                    entries=((action.direction, action.relative_path),),
                    recover_verified=True) != (action,):
                raise BackupExecutionError('source or destination changed in batch')
            results.append(transfer_one_approved(
                nas_root=nas_root, usb_root=usb_root, action=action,
                device_serial=device_serial))
            _writable_identity(mount=mount, by_id=by_id, uuid=uuid)
    # SupervisedWriteWindow.__exit__ must independently verify RO. Repeat RO
    # cartridge attestation before recording host-only receipts.
    if attest_read_only() != (uuid, device_serial, True):
        raise BackupExecutionError('cartridge not returned to verified read-only')
    for action in scope.actions:
        source_root, target_root = ((nas_root, usb_root) if action.direction == 'NAS_TO_USB'
                                   else (usb_root, nas_root))
        source, target = source_root / action.relative_path, target_root / action.relative_path
        _match_file(source, action)
        _match_file(target, action)
        if action.direction == 'NAS_TO_USB':
            commit_verified_backup(source=source, destination=target,
                manifest=backup_manifest, expected_size=action.size_bytes,
                expected_sha256=action.sha256)
        else:
            record_ingest(action, source, target)  # host-only, distinct ingest receipt
    return {'state': 'HOST_BIDIRECTIONAL_VERIFIED',
            'authorization_consumed': True, 'cartridge_read_only': True,
            'transfers': results}
