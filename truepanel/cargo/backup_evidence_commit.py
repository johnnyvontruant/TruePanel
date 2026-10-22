"""Fail-closed, non-hardware backup evidence commit and recovery.

Use only after trusted transaction has independently confirmed a physical copy.
This module is not a transfer authorization endpoint and does not mount media.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .backup_executor import BackupExecutionError

KIND = 'truepanel.cargo_backup_manifest'
CHUNK = 1024 * 1024


def _hash_regular(path: Path) -> tuple[int, str]:
    # Reject symlinks in every existing component (no path substitution is trusted).
    for p in (path, *path.parents):
        if p.is_symlink():
            raise BackupExecutionError('symlink in evidence path')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise BackupExecutionError('evidence file is not regular')
        h = hashlib.sha256()
        while part := os.read(fd, CHUNK):
            h.update(part)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size,
            before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_dev, after.st_ino, after.st_size,
            after.st_mtime_ns, after.st_ctime_ns):
            raise BackupExecutionError('evidence file changed while hashing')
        return before.st_size, h.hexdigest()
    finally:
        os.close(fd)


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {'schema_version': 1, 'kind': KIND,
                'source': 'loadmaster-verified-transaction',
                'created_at': datetime.now(timezone.utc).isoformat(), 'items': []}
    if path.is_symlink():
        raise BackupExecutionError('manifest symlink refused')
    try:
        raw = path.read_bytes()
        obj = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise BackupExecutionError('existing manifest unreadable or invalid') from exc
    if (not isinstance(obj, dict) or obj.get('schema_version') != 1
            or obj.get('kind') != KIND or not isinstance(obj.get('items'), list)):
        raise BackupExecutionError('manifest schema mismatch')
    try:
        # Original TruePanel manifests omit created_at. Preserve that
        # valid legacy schema and stamp created_at on successful merge.
        if 'created_at' in obj:
            datetime.fromisoformat(obj['created_at'].replace('Z', '+00:00'))
        assert isinstance(obj['source'], str) and obj['source']
        seen = set()
        for item in obj['items']:
            assert isinstance(item, dict)
            assert isinstance(item.get('path'), str) and item['path'].startswith('/')
            assert type(item.get('size_bytes')) is int and item['size_bytes'] >= 0
            assert isinstance(item.get('backed_up_at'), str)
            datetime.fromisoformat(item['backed_up_at'].replace('Z', '+00:00'))
            if 'sha256' in item:
                assert isinstance(item['sha256'], str)
                assert len(item['sha256']) == 64 and all(c in '0123456789abcdefABCDEF' for c in item['sha256'])
            assert item['path'] not in seen
            seen.add(item['path'])
    except (KeyError, ValueError, TypeError, AssertionError) as exc:
        raise BackupExecutionError('existing manifest has invalid entries') from exc
    return obj


def commit_verified_backup(*, source: Path, destination: Path,
                           manifest: Path, expected_size: int,
                           expected_sha256: str) -> dict[str, Any]:
    """Verify both copies again, atomically merge evidence; no media writes.

    An interrupted operation before commit is retryable: verify the already
    published destination, then write evidence. Never overwrites media files.
    Caller must independently establish cartridge identity, mount, and source
    mapping. This module alone does NOT authorize physical transfers.
    """
    if (not source.is_absolute() or not destination.is_absolute()
            or not manifest.is_absolute() or source == destination):
        raise BackupExecutionError('invalid evidence paths')
    if (type(expected_size) is not int or expected_size < 0
            or not isinstance(expected_sha256, str) or len(expected_sha256) != 64
            or any(c not in '0123456789abcdef' for c in expected_sha256)):
        raise BackupExecutionError('invalid expected evidence')
    # Serialize all cooperating writers by flock on persistent lock inode.
    parent = manifest.parent
    if not parent.is_dir() or parent.is_symlink() or manifest.is_symlink():
        raise BackupExecutionError('invalid manifest directory')
    lock_path = parent / ('.' + manifest.name + '.lock')
    if lock_path.is_symlink():
        raise BackupExecutionError('unsafe evidence lock')
    lockfd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    tmp = None
    try:
        fcntl.flock(lockfd, fcntl.LOCK_EX)
        source_size, source_hash = _hash_regular(source)
        dest_size, dest_hash = _hash_regular(destination)
        if (source_size != expected_size or dest_size != expected_size
                or source_hash != expected_sha256 or dest_hash != expected_sha256):
            raise BackupExecutionError('verified destination or source mismatch')
        obj = _read_manifest(manifest)
        item = {'path': str(source), 'size_bytes': expected_size,
                'backed_up_at': datetime.now(timezone.utc).isoformat(),
                'sha256': expected_sha256}
        old = [i for i in obj['items'] if i['path'] == str(source)]
        if old:
            # Do not overwrite different existing evidence for the same path.
            if any(i['size_bytes'] != expected_size or
                   (i.get('sha256') is not None and i['sha256'].lower() != expected_sha256)
                   for i in old):
                raise BackupExecutionError('conflicting existing backup evidence')
            return {'state': 'ALREADY_RECORDED', 'item': old[0], 'manifest_updated': False}
        obj['items'].append(item)
        obj['created_at'] = datetime.now(timezone.utc).isoformat()
        data = (json.dumps(obj, indent=2, sort_keys=True) + '\n').encode()
        fd, tmp_name = tempfile.mkstemp(prefix='.' + manifest.name + '.pending-', dir=parent)
        tmp = Path(tmp_name)
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # No concurrent writers from this module can race the replacement.
        # Non-cooperating external writers require host-level single-writer policy.
        os.replace(tmp, manifest)
        tmp = None
        dfd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
        return {'state': 'EVIDENCE_RECORDED', 'item': item, 'manifest_updated': True}
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
        fcntl.flock(lockfd, fcntl.LOCK_UN)
        os.close(lockfd)
