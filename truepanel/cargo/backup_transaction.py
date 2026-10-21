"""Fail-closed, one-file copy transaction.

A transport primitive, NOT a USB authorization endpoint. Only the host-owned
orchestrator may call this after verifying hardware and consuming a GPIO event.
No cartridge mounts, registry changes, or deletion of existing files.
"""
from __future__ import annotations

import hashlib
import ctypes
import os
import secrets
import stat
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .backup_executor import BackupExecutionError

CHUNK = 1024 * 1024


def _directory(fd: int, name: str, *, create: bool = False) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    if create:
        try:
            os.mkdir(name, 0o755, dir_fd=fd)
        except FileExistsError:
            pass
    return os.open(name, flags, dir_fd=fd)


def _hash_fd(fd: int) -> str:
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while data := os.read(fd, CHUNK):
        digest.update(data)
    return digest.hexdigest()


def _safe_parts(relative_path: str) -> tuple[str, ...]:
    rel = PurePosixPath(relative_path)
    if (not isinstance(relative_path, str) or not relative_path
            or rel.is_absolute() or str(rel) != relative_path
            or any(part in ('', '.', '..') for part in relative_path.split('/'))
            or '\x00' in relative_path or '\\' in relative_path):
        raise BackupExecutionError('unsafe transfer path')
    if len(rel.parts) != 2:
        raise BackupExecutionError('one-episode test requires show/file path')
    return rel.parts


def transfer_one_file(*, source_root: Path, usb_root: Path,
                      relative_path: str, expected_size: int,
                      sandbox_root: Path,
                      fault: str | None = None) -> dict:
    """Sandbox-only, one-episode transaction. No physical mount authority."""
    if fault not in (None, 'interrupt', 'corrupt', 'collision'):
        raise BackupExecutionError('unknown injected fault')
    if (type(expected_size) is not int or expected_size < 0
            or not source_root.is_absolute() or not usb_root.is_absolute()
            or source_root.is_symlink() or usb_root.is_symlink()):
        raise BackupExecutionError('invalid transaction input')
    # This development primitive is unable to target arbitrary paths or mounts.
    # Production execution requires a different, trusted host-owned entrypoint.
    if (not sandbox_root.is_absolute() or sandbox_root.is_symlink()
            or not sandbox_root.is_dir()):
        raise BackupExecutionError('invalid sandbox')
    sandbox = sandbox_root.resolve(strict=True)
    for root in (source_root, usb_root):
        if (root.is_symlink() or not root.is_dir()
                or root.resolve(strict=True).parent != sandbox
                or os.path.ismount(root)
                or root.stat().st_dev != sandbox.stat().st_dev):
            raise BackupExecutionError('transfer root outside sandbox')
    folder, filename = _safe_parts(relative_path)
    dflags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    nas = os.open(source_root, dflags)
    usb = None
    ns = None
    dest = None
    tmp_name = None
    try:
        usb = os.open(usb_root, dflags)
        ns = _directory(nas, folder)
        source_fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=ns)
        try:
            before = os.fstat(source_fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size != expected_size:
                raise BackupExecutionError('source changed from plan')
            # The lone allowed directory creation; no unrelated library changes.
            dest = _directory(usb, folder, create=True)
            try:
                existing = os.stat(filename, dir_fd=dest, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise BackupExecutionError('destination already exists')
            tmp_name = '.loadmaster-partial-' + secrets.token_hex(16)
            tmp_fd = os.open(tmp_name, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW,
                             0o600, dir_fd=dest)
            try:
                source_hash = hashlib.sha256()
                count = 0
                while data := os.read(source_fd, CHUNK):
                    count += len(data)
                    source_hash.update(data)
                    mv = memoryview(data)
                    while mv:
                        mv = mv[os.write(tmp_fd, mv):]
                    if fault == 'interrupt':
                        raise BackupExecutionError('injected interruption')
                os.fsync(tmp_fd)
                after = os.fstat(source_fd)
                if (count != expected_size or
                    (before.st_dev, before.st_ino, before.st_size,
                     before.st_mtime_ns, before.st_ctime_ns) !=
                    (after.st_dev, after.st_ino, after.st_size,
                     after.st_mtime_ns, after.st_ctime_ns)):
                    raise BackupExecutionError('source changed during copy')
                if fault == 'corrupt':
                    os.pwrite(tmp_fd, b'X', 0)
                    os.fsync(tmp_fd)
                if _hash_fd(tmp_fd) != source_hash.hexdigest():
                    raise BackupExecutionError('destination checksum mismatch')
            finally:
                os.close(tmp_fd)
            if fault == 'collision':
                fd = os.open(filename, os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                             0o600, dir_fd=dest)
                try:
                    os.write(fd, b'existing file')
                    os.fsync(fd)
                finally:
                    os.close(fd)
            # renameat2 operates directly on the pinned destination dirfd.
            libc = ctypes.CDLL(None, use_errno=True)
            rename = libc.renameat2
            rename.argtypes = [ctypes.c_int, ctypes.c_char_p,
                               ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            rename.restype = ctypes.c_int
            if rename(dest, os.fsencode(tmp_name), dest,
                      os.fsencode(filename), 1) != 0:
                err = ctypes.get_errno()
                raise BackupExecutionError(
                    f'atomic publication refused: {os.strerror(err)} (errno={err})'
                )
            tmp_name = None
            # After publication, verify again through pinned directory FD.
            published_fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dest)
            try:
                final = os.fstat(published_fd)
                if (not stat.S_ISREG(final.st_mode) or final.st_size != count or
                        _hash_fd(published_fd) != source_hash.hexdigest()):
                    raise BackupExecutionError('published file verification failed')
            finally:
                os.close(published_fd)
            os.fsync(dest)
            return {'state': 'VERIFIED_COPY', 'size_bytes': count,
                    'sha256': source_hash.hexdigest(), 'relative_path': relative_path,
                    'source_path': str(source_root / relative_path),
                    'destination_path': str(usb_root / relative_path)}
        finally:
            os.close(source_fd)
    finally:
        if tmp_name is not None and dest is not None:
            try:
                os.unlink(tmp_name, dir_fd=dest)
            except FileNotFoundError:
                pass
        for fd in (dest, ns, usb, nas):
            if fd is not None:
                os.close(fd)


def verified_manifest_item(result: dict) -> dict:
    """Build validated backup evidence solely for a verified transaction.

    Does NOT overwrite the shared backup manifest. That merge is an
    orchestration concern and must preserve existing entries.
    """
    if result.get('state') != 'VERIFIED_COPY':
        raise BackupExecutionError('no verified copy evidence')
    item = {'path': result['source_path'], 'size_bytes': result['size_bytes'],
            'backed_up_at': datetime.now(timezone.utc).isoformat(),
            'sha256': result['sha256']}
    payload = {'schema_version': 1, 'kind': 'truepanel.cargo_backup_manifest',
               'source': 'loadmaster-verified-transaction',
               'created_at': item['backed_up_at'], 'items': [item]}
    # Schema check in memory without writing any shared manifest.
    if (type(item['size_bytes']) is not int or len(item['sha256']) != 64 or
            not all(c in '0123456789abcdef' for c in item['sha256'])):
        raise BackupExecutionError('invalid copy evidence')
    return payload
