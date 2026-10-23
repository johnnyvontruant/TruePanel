"""Fail-closed, direction-bound Loadmaster host approval for mixed batches.

Staging integration component only. No GPIO reads, mounts, copying, transfers,
or USB mutation. A trusted host must independently attest the pinned cartridge
and own the Copy-button callback through LoadmasterHostSessionBridge.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .backup_executor import (
    BackupExecutionError, DurableConfirmationJournal,
    DurableHostAuthorizationSession,
)
from .backup_transaction import _safe_parts
from .os_housekeeping import ignored_os_path
from .copy_button import LoadmasterPhysicalPreflight

DIRECTIONS = frozenset({'NAS_TO_USB', 'USB_TO_NAS'})
MAX_FILES = 3


@dataclass(frozen=True)
class CargoAction:
    direction: str
    relative_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class CargoScope:
    cartridge_id: str
    cartridge_uuid: str
    device_serial: str
    actions: tuple[CargoAction, ...]
    attempt_nonce: str = field(default_factory=lambda: secrets.token_hex(16))

    @property
    def digest(self) -> str:
        validate_scope(self)
        canonical = {
            'contract': 'truepanel.loadmaster.bidirectional.physical.v1',
            'cartridge_id': self.cartridge_id,
            'cartridge_uuid': self.cartridge_uuid,
            'device_serial': self.device_serial,
            'attempt_nonce': self.attempt_nonce,
            'delete_policy': 'never',
            'overwrite_policy': 'never',
            'actions': [
                {'direction': a.direction, 'relative_path': a.relative_path,
                 'size_bytes': a.size_bytes, 'sha256': a.sha256}
                for a in self.actions
            ],
        }
        data = json.dumps(canonical, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=True).encode('ascii')
        return hashlib.sha256(data).hexdigest()


def validate_scope(scope: CargoScope) -> None:
    if type(scope) is not CargoScope or not 1 <= len(scope.actions) <= MAX_FILES:
        raise BackupExecutionError('invalid bidirectional batch')
    if (not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', scope.cartridge_id)
            or not re.fullmatch(r'[A-Fa-f0-9-]{4,80}', scope.cartridge_uuid)
            or not re.fullmatch(r'[A-Za-z0-9]{6,64}', scope.device_serial)):
        raise BackupExecutionError('invalid cartridge identity')
    if not re.fullmatch(r'[a-f0-9]{32}', scope.attempt_nonce):
        raise BackupExecutionError('invalid or missing fresh attempt nonce')
    seen = set()
    for item in scope.actions:
        if type(item) is not CargoAction or item.direction not in DIRECTIONS:
            raise BackupExecutionError('invalid cargo direction')
        _safe_parts(item.relative_path)  # existing descriptor-safe, two-level rule
        if ignored_os_path(item.relative_path):
            raise BackupExecutionError('OS housekeeping file not transferable')
        if item.relative_path in seen:
            raise BackupExecutionError('duplicate or cross-direction path')
        seen.add(item.relative_path)
        if (type(item.size_bytes) is not int or item.size_bytes <= 0
                or not re.fullmatch(r'[a-f0-9]{64}', item.sha256)):
            raise BackupExecutionError('invalid cargo fingerprint')


def _stat_and_hash(path: Path) -> tuple[int, str]:
    for segment in (path, *path.parents):
        if segment.is_symlink():
            raise BackupExecutionError('symlinked cargo path')
    try:
        before = path.stat()
        if not stat.S_ISREG(before.st_mode):
            raise BackupExecutionError('cargo source not regular')
        digest = hashlib.sha256()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            opened = os.fstat(fd)
            if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns,
                opened.st_ctime_ns) != (before.st_dev, before.st_ino, before.st_size,
                                      before.st_mtime_ns, before.st_ctime_ns):
                raise BackupExecutionError('source changed before inspection')
            while chunk := os.read(fd, 1024 * 1024):
                digest.update(chunk)
            after = os.fstat(fd)
            if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
                after.st_ctime_ns) != (opened.st_dev, opened.st_ino, opened.st_size,
                                     opened.st_mtime_ns, opened.st_ctime_ns):
                raise BackupExecutionError('source changed during inspection')
        finally:
            os.close(fd)
        final = path.stat()
        if (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns,
            final.st_ctime_ns) != (before.st_dev, before.st_ino, before.st_size,
                                 before.st_mtime_ns, before.st_ctime_ns):
            raise BackupExecutionError('source changed during inspection')
        return before.st_size, digest.hexdigest()
    except OSError as err:
        raise BackupExecutionError('cannot inspect cargo file') from err


def inspect_bidirectional(*, nas_root: Path, usb_root: Path,
                          entries: tuple[tuple[str, str], ...],
                          recover_verified: bool = False) -> tuple[CargoAction, ...]:
    """Build a read-only plan; verify published recovery copies but never replace.

    This is a planner, not hardware attestation. The host must separately
    attest the USB by-id device/UUID and ensure usb_root belongs to its mount.
    """
    if (not isinstance(nas_root, Path) or not isinstance(usb_root, Path)
            or not all(p.is_absolute() and p.is_dir() and not p.is_symlink()
                       for p in (nas_root, usb_root))
            or nas_root == usb_root or type(entries) is not tuple
            or not 1 <= len(entries) <= MAX_FILES):
        raise BackupExecutionError('invalid read-only inspection roots or entries')
    for root in (nas_root, usb_root):
        for parent in root.parents:
            if parent.is_symlink():
                raise BackupExecutionError('symlinked cargo root')
    planned = []
    seen = set()
    for entry in entries:
        if type(entry) is not tuple or len(entry) != 2:
            raise BackupExecutionError('invalid transfer entry')
        direction, relative = entry
        if direction not in DIRECTIONS:
            raise BackupExecutionError('unsupported transfer direction')
        _safe_parts(relative)
        if ignored_os_path(relative):
            raise BackupExecutionError('OS housekeeping file excluded from physical plan')
        if relative in seen:
            raise BackupExecutionError('duplicate or cross-direction destination')
        seen.add(relative)
        source_root, dest_root = (nas_root, usb_root) if direction == 'NAS_TO_USB' else (usb_root, nas_root)
        source = source_root / relative
        destination = dest_root / relative
        size, sha256 = _stat_and_hash(source)
        for segment in (destination, destination.parent):
            if segment.is_symlink():
                raise BackupExecutionError('symlinked cargo destination')
        if os.path.lexists(destination):
            if not recover_verified:
                raise BackupExecutionError('cargo destination already occupied')
            dest_size, dest_sha256 = _stat_and_hash(destination)
            if (dest_size, dest_sha256) != (size, sha256):
                raise BackupExecutionError('recovery destination conflict')
        planned.append(CargoAction(direction, relative, size, sha256))
    return tuple(planned)


class HostBidirectionalApprovalSession:
    """Implements the existing host bridge's session interface, no actuation.

    The serial and transfer direction are included in the exact digest, unlike
    the legacy NAS-only batch contract. Approvals burn durably before a caller
    may hand control to a separately qualified physical actuator.
    """
    def __init__(self, *, fresh_actions: Callable[[], tuple[CargoAction, ...]],
                 attest_identity: Callable[[], tuple[str, str, bool]],
                 clock=time.monotonic):
        if not callable(fresh_actions) or not callable(attest_identity):
            raise BackupExecutionError('host attestation and reinspection required')
        self._fresh = fresh_actions
        self._attest_identity = attest_identity
        self._clock = clock
        self._state = 'NEW'
        self._scope: CargoScope | None = None
        self._authorization = None
        self._digest = None

    def _check_identity(self, scope: CargoScope) -> None:
        observed = self._attest_identity()
        if (type(observed) is not tuple or
                observed != (scope.cartridge_uuid, scope.device_serial, True)):
            raise BackupExecutionError('cartridge identity or RO state changed')

    def prepare(self, spec: tuple[CargoScope, Path]) -> LoadmasterPhysicalPreflight:
        if self._state != 'NEW':
            raise BackupExecutionError('bidirectional session already used')
        if (type(spec) is not tuple or len(spec) != 2 or
                type(spec[0]) is not CargoScope or not isinstance(spec[1], Path)):
            raise BackupExecutionError('invalid direction-bound session spec')
        scope, journal_root = spec
        validate_scope(scope)
        if not journal_root.is_absolute() or journal_root.is_symlink():
            raise BackupExecutionError('unsafe approval journal root')
        self._check_identity(scope)
        if self._fresh() != scope.actions:
            raise BackupExecutionError('bidirectional plan changed before arm')
        digest = scope.digest
        authorization = DurableHostAuthorizationSession(
            clock=self._clock, journal=DurableConfirmationJournal(journal_root))
        authorization.arm(cartridge_id=scope.cartridge_id,
                          cartridge_uuid=scope.cartridge_uuid,
                          device_serial=scope.device_serial, plan_digest=digest)
        self._authorization = authorization
        self._scope = scope
        self._digest = digest
        self._state = 'ARMED'
        return LoadmasterPhysicalPreflight(
            cartridge_id=scope.cartridge_id, cartridge_uuid=scope.cartridge_uuid,
            device_serial=scope.device_serial, plan_state='READY',
            backup_files=len(scope.actions),  # generic existing GPIO count field
            backup_bytes=sum(a.size_bytes for a in scope.actions),
            baseline_verified=True, identity_verified=True, backlog_verified=True,
            plan_digest=digest, generated_at_monotonic=self._clock())

    def on_confirmation(self, confirmation) -> None:
        if self._state != 'ARMED':
            raise BackupExecutionError('bidirectional session not armed')
        self._authorization.on_confirmation(confirmation)

    def consume_after_physical_press(self) -> dict:
        if self._state != 'ARMED':
            raise BackupExecutionError('bidirectional approval unavailable')
        self._state = 'SPENT'
        try:
            self._check_identity(self._scope)
            if self._fresh() != self._scope.actions:
                raise BackupExecutionError('bidirectional plan changed after press')
            receipt = self._authorization.consume()
            if receipt['plan_digest'] != self._digest:
                raise BackupExecutionError('direction-bound confirmation digest mismatch')
            return {**receipt, 'state': 'HOST_APPROVAL_EVIDENCE_ONLY',
                    'physical_execution_enabled': False, 'executed': False}
        finally:
            self._authorization.disarm()

    def disarm(self) -> None:
        self._state = 'SPENT'
        if self._authorization is not None:
            self._authorization.disarm()

    def execute_physical(self, *args, **kwargs) -> None:
        raise BackupExecutionError('BIDIRECTIONAL_PHYSICAL_EXECUTION_NOT_QUALIFIED')
