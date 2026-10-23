"""Resumable rsync transport, restricted to a disposable NON-MOUNTED sandbox.

No GPIO or USB authority. Host production actuator deliberately NOT wired.
Partial state is retained on failure and never represents authorization.
"""
from __future__ import annotations
import ctypes
import hashlib
import os
from pathlib import Path
import subprocess

from .backup_executor import BackupExecutionError
from .backup_transaction import _safe_parts, _directory

def _sha256(path: Path) -> tuple[int, str]:
    if path.is_symlink() or not path.is_file():
        raise BackupExecutionError('unsafe transport file')
    h = hashlib.sha256()
    before = path.stat()
    with path.open('rb') as f:
        while data := f.read(1024 * 1024):
            h.update(data)
        during = os.fstat(f.fileno())
    after = path.stat()
    stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if stamp(before) != stamp(during) or stamp(before) != stamp(after):
        raise BackupExecutionError('file changed during hash')
    return before.st_size, h.hexdigest()

def rsync_sandbox_copy(*, sandbox: Path, source_root: Path,
                       destination_root: Path, relative_path: str,
                       expected_size: int, expected_sha256: str,
                       timeout_seconds: int = 120) -> dict:
    """Only copy when separately invoked; retry requires a new invocation.

    Destination is atomically published with renameat2(RENAME_NOREPLACE).
    """
    folder, filename = _safe_parts(relative_path)
    if (not sandbox.is_absolute() or sandbox.is_symlink() or not sandbox.is_dir()
        or source_root.is_symlink() or destination_root.is_symlink()
        or not all(p.is_absolute() for p in (source_root, destination_root))
        or type(expected_size) is not int or expected_size < 0
        or len(expected_sha256) != 64
        or any(ch not in '0123456789abcdef' for ch in expected_sha256)
        or type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 3600):
        raise BackupExecutionError('unsafe rsync transport context')
    parent = sandbox.resolve(strict=True)
    for root in (source_root, destination_root):
        if (not root.is_dir() or root.resolve(strict=True).parent != parent
            or os.path.ismount(root) or root.stat().st_dev != parent.stat().st_dev):
            raise BackupExecutionError('rsync transport limited to disposable sandbox')
    source = source_root / folder / filename
    target = destination_root / folder / filename
    if source.parent.is_symlink() or target.parent.is_symlink() or os.path.lexists(target):
        raise BackupExecutionError('unsafe or occupied final destination')
    if _sha256(source) != (expected_size, expected_sha256):
        raise BackupExecutionError('source disagrees with approved snapshot')
    work_dir = destination_root / '.loadmaster-rsync-stage'
    work_dir.mkdir(mode=0o700, exist_ok=True)
    if work_dir.is_symlink():
        raise BackupExecutionError('stage symlink rejected')
    staged_name = hashlib.sha256(
        (relative_path + '\0' + expected_sha256).encode()).hexdigest()
    staged = work_dir / staged_name
    if staged.is_symlink():
        raise BackupExecutionError('staged file symlink rejected')
    # rsync keeps interrupted data in a private partial-dir on the same
    # filesystem. Never pass --inplace, --append or --delete.
    cmd = ['rsync', '--checksum', '--partial-dir=.loadmaster-partials',
           '--no-owner', '--no-group', '--', str(source), str(staged)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired as exc:
        raise BackupExecutionError('rsync timed out; partial kept for a newly authorized retry') from exc
    if proc.returncode:
        raise BackupExecutionError(f'rsync returned {proc.returncode}; partial retained for retry')
    if _sha256(source) != (expected_size, expected_sha256):
        raise BackupExecutionError('source changed after rsync')
    if _sha256(staged) != (expected_size, expected_sha256):
        raise BackupExecutionError('staged destination checksum mismatch')
    dflags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    destfd = os.open(destination_root, dflags)
    workfd = None
    folderfd = None
    try:
        workfd = _directory(destfd, '.loadmaster-rsync-stage')
        folderfd = _directory(destfd, folder, create=True)
        libc = ctypes.CDLL(None, use_errno=True)
        rename = libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(workfd, os.fsencode(staged_name), folderfd, os.fsencode(filename), 1) != 0:
            errno = ctypes.get_errno()
            raise BackupExecutionError(f'no-overwrite publication refused: {os.strerror(errno)}')
        os.fsync(folderfd)
    finally:
        for fd in (folderfd, workfd, destfd):
            if fd is not None:
                os.close(fd)
    if _sha256(target) != (expected_size, expected_sha256):
        raise BackupExecutionError('published file did not verify')
    return {'state':'RSYNC_SANDBOX_VERIFIED', 'relative_path':relative_path,
            'size_bytes':expected_size, 'sha256':expected_sha256,
            'authorization_supplied_by_transport':False}
