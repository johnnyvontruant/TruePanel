"""Read-only, fail-closed transaction inspection. NOT physical execution authority."""
from __future__ import annotations
import hashlib
import os
import stat
from pathlib import Path
from typing import Any
from .backup_executor import BackupExecutionError
from .physical_readiness import probe_one_episode


def _safe_chain(path: Path, *, require_final: bool = False) -> None:
    for candidate in (path, *path.parents):
        if candidate.is_symlink():
            raise BackupExecutionError(f'symlink in path: {candidate}')
    if require_final and not path.is_file():
        raise BackupExecutionError('source unavailable')


def inspect_transaction(*, registry: Path, backlog: Path, cartridge_id: str,
                        mount: Path, by_id: str, source_path: Path) -> dict[str, Any]:
    """Hash source, check unoccupied destination, then re-probe physical plan.

    This is advisory evidence. It does not lock files or provide TOCTOU-safe
    execution authorization and MUST NOT be reused as an actuator preflight.
    """
    initial = probe_one_episode(registry=registry, backlog=backlog,
        cartridge_id=cartridge_id, mount=mount, by_id=by_id,
        source_path=source_path)
    if not initial['device_serial_registered']:
        raise BackupExecutionError('hardware serial not registered')
    relative = Path(initial['relative_path'])
    if relative.is_absolute() or not relative.parts or '..' in relative.parts or '.' in relative.parts:
        raise BackupExecutionError('unsafe relative path')
    _safe_chain(source_path, require_final=True)
    from .cartridges import load_cartridge_registry
    registered = [c for c in load_cartridge_registry(registry) if c.cartridge_id == cartridge_id]
    if len(registered) != 1:
        raise BackupExecutionError('ambiguous cartridge')
    usb_root = mount / registered[0].usb_relative_path
    destination = usb_root / relative
    _safe_chain(usb_root)
    _safe_chain(destination)
    if not usb_root.is_dir():
        raise BackupExecutionError('USB library root missing')
    if os.path.lexists(destination):
        raise BackupExecutionError('destination occupied')
    before = source_path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode) or before.st_size != initial['size_bytes']:
        raise BackupExecutionError('source changed')
    free = os.statvfs(mount)
    free_bytes = free.f_bavail * free.f_frsize
    if free_bytes < initial['size_bytes']:
        raise BackupExecutionError('insufficient cartridge capacity')
    digest = hashlib.sha256()
    with source_path.open('rb') as reader:
        opened = os.fstat(reader.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size):
            raise BackupExecutionError('source replaced during open')
        while chunk := reader.read(1024 * 1024):
            digest.update(chunk)
        after_fd = os.fstat(reader.fileno())
    after = source_path.stat(follow_symlinks=False)
    for value in (after_fd, after):
        if (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns) != (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns):
            raise BackupExecutionError('source changed while hashing')
    _safe_chain(destination)
    if os.path.lexists(destination):
        raise BackupExecutionError('destination appeared while hashing')
    final = probe_one_episode(registry=registry, backlog=backlog,
        cartridge_id=cartridge_id, mount=mount, by_id=by_id, source_path=source_path)
    if final != initial:
        raise BackupExecutionError('read-only plan changed during hashing')
    return {
        **final, 'state': 'READ_ONLY_TRANSACTION_ACCEPTED',
        'source_sha256': digest.hexdigest(), 'available_bytes': free_bytes,
        'destination': str(destination), 'destination_absent': True,
        'executed': False, 'backup_authorized': False,
    }
