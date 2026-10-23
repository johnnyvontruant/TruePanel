"""Loadmaster bidirectional, read-only discovery for two-level media paths.

Stage-only. Classification does not grant either side write authority.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path

from .backup_executor import BackupExecutionError
from .backup_transaction import _safe_parts

@dataclass(frozen=True)
class CargoDecision:
    relative_path: str
    classification: str
    nas_sha256: str | None
    usb_sha256: str | None
    size_bytes: int | None

def _inventory(root: Path) -> dict[str, tuple[int, str]]:
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise BackupExecutionError('invalid inventory root')
    result = {}
    for directory in root.iterdir():
        if directory.name.startswith('.') or directory.name.startswith('LOADMASTER-'):
            continue
        if directory.is_symlink():
            raise BackupExecutionError('symlink folder rejected')
        if not directory.is_dir():
            continue
        for entry in directory.iterdir():
            if entry.is_symlink():
                raise BackupExecutionError('symlink item rejected')
            if not entry.is_file():
                continue
            relative = f'{directory.name}/{entry.name}'
            _safe_parts(relative)
            before = entry.stat()
            h = hashlib.sha256()
            with entry.open('rb') as stream:
                fd_before = os.fstat(stream.fileno())
                if (fd_before.st_ino, fd_before.st_size) != (before.st_ino, before.st_size):
                    raise BackupExecutionError('inventory race')
                while chunk := stream.read(1024 * 1024):
                    h.update(chunk)
                fd_after = os.fstat(stream.fileno())
            after = entry.stat()
            fingerprint = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if fingerprint(before) != fingerprint(fd_after) or fingerprint(before) != fingerprint(after):
                raise BackupExecutionError('source changed during inventory')
            result[relative] = (before.st_size, h.hexdigest())
    return result

def discover_bidirectional(*, nas_root: Path, usb_root: Path) -> dict:
    """No writes. Treat content disagreements as conflicts, never deletions."""
    if nas_root.resolve() == usb_root.resolve():
        raise BackupExecutionError('source and destination are identical')
    nas, usb = _inventory(nas_root), _inventory(usb_root)
    items = []
    counts = {'export_to_usb': 0, 'ingest_to_nas': 0, 'verified_match': 0, 'conflict': 0}
    for relative in sorted(nas.keys() | usb.keys()):
        left, right = nas.get(relative), usb.get(relative)
        if left is None:
            cls = 'ingest_to_nas'
        elif right is None:
            cls = 'export_to_usb'
        elif left == right:
            cls = 'verified_match'
        else:
            cls = 'conflict'
        counts[cls] += 1
        items.append(asdict(CargoDecision(relative, cls,
                                         left[1] if left else None,
                                         right[1] if right else None,
                                         (left or right)[0])))
    return {'state': 'READ_ONLY_CARGO_DISCOVERY', 'counts': counts, 'items': items,
            'authorized': False, 'deleted': False}
