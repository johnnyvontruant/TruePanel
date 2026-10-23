"""Sandbox-only Loadmaster batch bridge with crash-durable approval consumption.

Do not deploy as a hardware/USB executor. Only accepts a marked disposable
/tmp or /var/tmp lab containing nas/ and usb/ on one filesystem. An authentic
host confirmation source is NOT established by this module: the button event
passed by tests is synthesized with LoadmasterCopyButtonGate.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import time
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from .copy_button import CopyButtonConfirmation
from .resumable_rsync_lab import Intent, LabError, _lab, _safe_path, _sync_dir, plan, transfer

MAX_ACTIONS = 100
MAX_CONFIRMATION_AGE = 30.0


class BatchError(LabError):
    """A batch safety precondition or durable approval check failed."""


@dataclass(frozen=True)
class Batch:
    cartridge_id: str
    cartridge_uuid: str
    device_serial: str
    actions: tuple[Intent, ...]
    attempt_nonce: str


def _validate_batch(batch: Batch) -> None:
    if not isinstance(batch, Batch):
        raise BatchError('invalid batch')
    if any(not isinstance(v, str) or not v or '\x00' in v or len(v) > 128
           for v in (batch.cartridge_id, batch.cartridge_uuid, batch.device_serial)):
        raise BatchError('invalid cartridge identity')
    if not re.fullmatch(r'[0-9a-f]{32}', batch.attempt_nonce):
        raise BatchError('invalid attempt nonce')
    if not (1 <= len(batch.actions) <= MAX_ACTIONS):
        raise BatchError('invalid batch size')
    seen: set[str] = set()
    for a in batch.actions:
        if (not isinstance(a, Intent) or a.direction not in {'NAS_TO_USB', 'USB_TO_NAS'}
                or not isinstance(a.relative, str) or not a.relative
                or not isinstance(a.size, int) or isinstance(a.size, bool) or a.size < 0
                or not isinstance(a.sha256, str)
                or not re.fullmatch('[0-9a-f]{64}', a.sha256)):
            raise BatchError('invalid batch action')
        if a.relative in seen:
            raise BatchError('duplicate or cross-direction conflicting path')
        seen.add(a.relative)


def plan_batch(root: Path, *, cartridge_id: str, cartridge_uuid: str,
               device_serial: str, entries: list[tuple[str, str]]) -> Batch:
    """Calculate immutable intent using read-only discovery of lab files."""
    _lab(root)
    if not isinstance(entries, list):
        raise BatchError('invalid entry list')
    actions = tuple(plan(root, direction=direction, relative=relative)
                    for direction, relative in entries)
    batch = Batch(cartridge_id, cartridge_uuid, device_serial, actions,
                  secrets.token_hex(16))
    _validate_batch(batch)
    return batch


def reapprove_batch(batch: Batch) -> Batch:
    """Change approval identity; preserve exact intended actions and cartridge."""
    _validate_batch(batch)
    return replace(batch, attempt_nonce=secrets.token_hex(16))


def batch_digest(batch: Batch) -> str:
    _validate_batch(batch)
    payload = {
        'schema_version': 1,
        'cartridge_id': batch.cartridge_id,
        'cartridge_uuid': batch.cartridge_uuid,
        'device_serial': batch.device_serial,
        'attempt_nonce': batch.attempt_nonce,
        'actions': [{'direction': a.direction, 'relative': a.relative,
                     'size': a.size, 'sha256': a.sha256} for a in batch.actions],
        'delete_policy': 'never',
        'overwrite_policy': 'never',
    }
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def _validate_confirmation(batch: Batch, confirmation: CopyButtonConfirmation,
                           *, clock: Callable[[], float]) -> None:
    if not isinstance(confirmation, CopyButtonConfirmation):
        raise BatchError('physical confirmation required')
    if (confirmation.plan_digest != batch_digest(batch)
            or confirmation.cartridge_id != batch.cartridge_id
            or confirmation.cartridge_uuid != batch.cartridge_uuid
            or confirmation.device_serial != batch.device_serial
            or confirmation.source != 'fintek_gpio75' or confirmation.bank != 7
            or confirmation.bit != 5 or confirmation.active_low is not True):
        raise BatchError('confirmation does not match immutable approved batch')
    age = clock() - confirmation.confirmed_at_monotonic
    if age < 0 or age > MAX_CONFIRMATION_AGE:
        raise BatchError('physical confirmation expired or from future')


def _journal(root: Path) -> Path:
    _lab(root)
    p = _safe_path(root, '.loadmaster-batch-lab-journal')
    if p.exists() and (not p.is_dir() or p.is_symlink()):
        raise BatchError('journal path occupied')
    p.mkdir(mode=0o700, exist_ok=True)
    return p


@contextmanager
def _lock_journal(root: Path):
    p = _journal(root)
    lockname = _safe_path(p, '.lock')
    fd = os.open(lockname, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise BatchError('batch journal already locked') from error
        yield p
    finally:
        os.close(fd)


def _durable_write_new(path: Path, record: dict) -> None:
    """Exclusive create is the durable point where an approval is consumed."""
    raw = (json.dumps(record, sort_keys=True, indent=2) + '\n').encode('utf-8')
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError as error:
        raise BatchError('approval replay: attempt already consumed') from error
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    _sync_dir(path.parent)


def _durable_update(path: Path, record: dict) -> None:
    """Atomic journal revision, preserving the consumed-approval filename."""
    tmp = path.parent / ('.' + secrets.token_hex(16) + '.tmp')
    try:
        _durable_write_new(tmp, record)
        os.replace(tmp, path)
        _sync_dir(path.parent)
    finally:
        if tmp.exists():
            tmp.unlink()


def read_receipt(root: Path, batch: Batch) -> dict | None:
    """Read a bounded JSON receipt without granting permission to transfer."""
    p = _safe_path(_journal(root), batch_digest(batch) + '.json')
    if not p.exists():
        return None
    if p.is_symlink() or not p.is_file() or p.stat().st_size > 100_000:
        raise BatchError('invalid durable receipt')
    result = json.loads(p.read_text())
    if (result.get('digest') != batch_digest(batch)
            or result.get('schema_version') != 1):
        raise BatchError('receipt identity mismatch')
    return result


def execute_batch(root: Path, batch: Batch, confirmation: CopyButtonConfirmation,
                  *, clock: Callable[[], float] = time.monotonic,
                  interrupt_index: int | None = None,
                  interrupt_after: float | None = None,
                  bwlimit_kib: int | None = None,
                  verify_environment: Callable[[], None] | None = None) -> dict:
    """Consume a single-use confirmation BEFORE any file copies.

    The host GPIO reader, USB identity attestation, mount write-window manager,
    production receipt writer, and trusted destination fd pinning are absent.
    Consequently this function will always reject non-disposable paths.
    """
    _lab(root)
    _validate_batch(batch)
    _validate_confirmation(batch, confirmation, clock=clock)
    if verify_environment is not None:
        verify_environment()
    digest = batch_digest(batch)
    with _lock_journal(root) as directory:
        receipt_file = _safe_path(directory, digest + '.json')
        receipt = {
            'schema_version': 1, 'digest': digest, 'state': 'CONSUMED',
            'cartridge_id': batch.cartridge_id,
            'cartridge_uuid': batch.cartridge_uuid,
            'action_count': len(batch.actions),
            'verified': [], 'incomplete': [i for i in range(len(batch.actions))],
            'attempt_nonce': batch.attempt_nonce,
            'sandbox_only': True,
        }
        _durable_write_new(receipt_file, receipt)
        try:
            for idx, intent in enumerate(batch.actions):
                if verify_environment is not None:
                    verify_environment()
                # Original actions are immutable across interrupted approvals.
                result = transfer(
                    root, intent, transfer_approved=True,
                    interrupt_after=interrupt_after if idx == interrupt_index else None,
                    bwlimit_kib=bwlimit_kib if idx == interrupt_index else None,
                )
                if verify_environment is not None:
                    verify_environment()
                receipt['verified'].append({
                    'index': idx, 'direction': intent.direction,
                    'relative': intent.relative, 'size': intent.size,
                    'sha256': intent.sha256, 'state': result['state'],
                })
                receipt['incomplete'].remove(idx)
                receipt['state'] = 'IN_PROGRESS' if receipt['incomplete'] else 'COMPLETE'
                _durable_update(receipt_file, receipt)
        except Exception as error:
            receipt['state'] = 'INTERRUPTED'
            receipt['error_class'] = type(error).__name__
            _durable_update(receipt_file, receipt)
            raise
        return dict(receipt)
