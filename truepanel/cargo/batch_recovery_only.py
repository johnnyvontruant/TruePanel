"""Strict recovery-only batch reconciliation on disposable storage.

Unlike batch execution, recovery never creates media files. It only verifies
already-published matching copies and records missing manifest evidence.
This module is sandbox-only and grants no physical USB authority.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Sequence

from .backup_evidence_commit import commit_verified_backup
from .backup_executor import BackupExecutionError
from .backup_transaction import _safe_parts


def _hash(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        while data := stream.read(1024 * 1024):
            value.update(data)
    return value.hexdigest()


def reconcile_sandbox_batch(*, sandbox_root: Path, nas: Path, usb: Path,
                            manifest: Path, names: Sequence[str]) -> dict:
    if (not 1 <= len(names) <= 3 or len(set(names)) != len(names)
            or any(not isinstance(name, str) for name in names)):
        raise BackupExecutionError('invalid recovery scope')
    if (not sandbox_root.is_absolute() or not sandbox_root.is_dir()
            or sandbox_root.is_symlink() or manifest.parent != sandbox_root
            or manifest.is_symlink()):
        raise BackupExecutionError('recovery manifest outside sandbox')
    root = sandbox_root.resolve(strict=True)
    for folder in (nas, usb):
        if (not folder.is_absolute() or not folder.is_dir()
                or folder.is_symlink() or os.path.ismount(folder)
                or folder.resolve(strict=True).parent != root
                or folder.stat().st_dev != root.stat().st_dev):
            raise BackupExecutionError('recovery roots outside sandbox')
    candidates = []
    incomplete = []
    for name in names:
        directory, filename = _safe_parts(name)
        source = nas / directory / filename
        destination = usb / directory / filename
        if (source.is_symlink() or source.parent.is_symlink()
                or not source.is_file() or destination.is_symlink()
                or destination.parent.is_symlink()):
            raise BackupExecutionError('unsafe recovery entry')
        if not destination.exists():
            incomplete.append(name)
            continue
        if not destination.is_file():
            raise BackupExecutionError('nonregular destination')
        length = source.stat().st_size
        source_hash = _hash(source)
        if destination.stat().st_size != length or _hash(destination) != source_hash:
            raise BackupExecutionError('published destination mismatch')
        candidates.append((name, source, destination, length, source_hash))
    recovered = []
    for name, source, destination, length, digest in candidates:
        result = commit_verified_backup(source=source,
            destination=destination, manifest=manifest,
            expected_size=length, expected_sha256=digest)
        recovered.append({'relative_path': name, 'manifest_state': result['state']})
    return {'state': 'SANDBOX_RECOVERY_ONLY', 'reconciled': recovered,
            'incomplete': incomplete, 'new_copies': 0,
            'physical_authorized': False, 'resumable_without_new_press': False}
