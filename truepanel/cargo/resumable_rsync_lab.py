"""Loadmaster bidirectional rsync interruption lab, NOT a physical-transfer API.

Disposable temp directories only. This module NEVER mounts disks, accesses GPIO,
updates TruePanel's real manifest, or grants backup/ingest authority.
"""
from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import re
import signal
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


class LabError(RuntimeError):
    pass


class InterruptedTransfer(LabError):
    pass


@dataclass(frozen=True)
class Intent:
    direction: str
    relative: str
    size: int
    sha256: str


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def _safe_path(root: Path, relative: str) -> Path:
    if (not isinstance(relative, str) or not relative or '\\' in relative or '\x00' in relative
        or relative.startswith('/') or any(p in ('', '.', '..') for p in relative.split('/'))):
        raise LabError('unsafe relative path')
    path = root
    for part in relative.split('/'):
        path = path / part
        if path.is_symlink():
            raise LabError('symlink in transfer path')
    return path


def _lab(root: Path) -> tuple[Path, Path]:
    if not root.is_absolute() or root.is_symlink():
        raise LabError('absolute non-symlink lab root required')
    p = root.resolve(strict=True)
    if not ((p.is_relative_to('/tmp/') or p.is_relative_to('/var/tmp/'))
            and p != Path('/tmp') and p != Path('/var/tmp')):
        raise LabError('only disposable temp labs allowed')
    marker = p / '.loadmaster-lab-only'
    if marker.is_symlink() or not marker.is_file() or marker.read_text() != 'LAB_ONLY\n':
        raise LabError('missing disposable lab marker')
    nas, usb = p/'nas', p/'usb'
    if any(not d.is_dir() or d.is_symlink() or d.resolve() != d for d in (nas, usb)):
        raise LabError('unsafe lab directories')
    if (os.path.ismount(p) or os.path.ismount(nas) or os.path.ismount(usb)
            or any(d.stat().st_dev != p.stat().st_dev for d in (nas, usb))):
        raise LabError('mounted media forbidden in disposable test lab')
    return nas, usb


def _paths(root: Path, direction: str, relative: str) -> tuple[Path, Path, Path]:
    nas, usb = _lab(root)
    if direction == 'NAS_TO_USB':
        source_root, dest_root = nas, usb
    elif direction == 'USB_TO_NAS':
        source_root, dest_root = usb, nas
    else:
        raise LabError('unsupported direction')
    return _safe_path(source_root, relative), _safe_path(dest_root, relative), dest_root


def _regular(path: Path) -> os.stat_result:
    if path.is_symlink():
        raise LabError('symlink refused')
    st = path.stat()
    if not stat.S_ISREG(st.st_mode):
        raise LabError('source is not a regular file')
    return st


def plan(root: Path, *, direction: str, relative: str) -> Intent:
    source, dest, _ = _paths(root, direction, relative)
    st = _regular(source)
    if dest.exists() or dest.is_symlink():
        raise LabError('destination occupied')
    return Intent(direction, relative, st.st_size, _digest(source))


def _noreplace_rename(source: Path, destination: Path) -> None:
    # Linux renameat2(RENAME_NOREPLACE), including exFAT when supported.
    lib = ctypes.CDLL(None, use_errno=True)
    rename = getattr(lib, 'renameat2', None)
    if rename is None:
        raise LabError('atomic no-replace rename unavailable')
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                       ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    rc = rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    if rc != 0:
        e = ctypes.get_errno()
        if e == errno.EEXIST:
            raise LabError('destination collision at publication')
        raise OSError(e, os.strerror(e))


def _sync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def transfer(root: Path, intent: Intent, *, transfer_approved: bool = False,
             interrupt_after: float | None = None, bwlimit_kib: int | None = None) -> dict:
    """Resume an incomplete staged transfer only after explicit lab approval.

    Existing published targets may be verified without transfer approval. The
    returned result is lab evidence, not the TruePanel production receipt.
    """
    if not isinstance(intent, Intent) or not re.fullmatch(r'[0-9a-f]{64}', intent.sha256):
        raise LabError('invalid intent')
    source, destination, dest_root = _paths(root, intent.direction, intent.relative)
    before = _regular(source)
    if before.st_size != intent.size or _digest(source) != intent.sha256:
        raise LabError('source differs from approved intent')
    if destination.exists() or destination.is_symlink():
        st = _regular(destination)
        if st.st_size == intent.size and _digest(destination) == intent.sha256:
            return {'state': 'PUBLISHED_ALREADY_VERIFIED', 'bytes': intent.size,
                    'new_transfer': False, 'direction': intent.direction}
        raise LabError('existing destination differs; never overwrite')
    if not transfer_approved:
        raise LabError('fresh transfer approval required')
    job = hashlib.sha256((intent.direction + '\n' + intent.relative + '\n' +
                          intent.sha256 + '\n' + str(intent.size)).encode()).hexdigest()
    stage_root = _safe_path(dest_root, '.loadmaster-rsync-stage')
    job_dir = _safe_path(stage_root, job)
    stage_file = _safe_path(job_dir, 'payload')
    for d in (stage_root, job_dir):
        if d.exists() and not d.is_dir():
            raise LabError('stage directory occupied')
        d.mkdir(mode=0o700, exist_ok=True)
    if stage_file.is_symlink():
        raise LabError('stage file symlink')
    args = ['rsync', '-t', '--no-whole-file', '--partial', '--partial-dir=.partials', '--stats',
            '--no-perms', '--no-owner', '--no-group']
    if bwlimit_kib is not None:
        if not isinstance(bwlimit_kib, int) or bwlimit_kib < 1:
            raise LabError('invalid lab bandwidth limit')
        args.append(f'--bwlimit={bwlimit_kib}')
    args.extend(['--', str(source), str(stage_file)])
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, start_new_session=True)
    if interrupt_after is not None:
        if interrupt_after <= 0:
            raise LabError('invalid interruption timing')
        time.sleep(interrupt_after)
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGINT)
    stdout, stderr = p.communicate(timeout=60)
    if p.returncode != 0:
        raise InterruptedTransfer(f'rsync stopped rc={p.returncode}; partial retained: {stderr[-300:]}')
    after = _regular(source)
    if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
         before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size,
                                  after.st_mtime_ns, after.st_ctime_ns)
        or _digest(source) != intent.sha256):
        raise LabError('source changed during transfer')
    if _regular(stage_file).st_size != intent.size or _digest(stage_file) != intent.sha256:
        raise LabError('staged content failed SHA-256')
    if destination.exists() or destination.is_symlink():
        raise LabError('destination appeared during transfer')
    destination.parent.mkdir(parents=True, exist_ok=True)
    _safe_path(dest_root, intent.relative)
    with stage_file.open('rb') as f:
        os.fsync(f.fileno())
    _noreplace_rename(stage_file, destination)
    _sync_dir(destination.parent)
    if _regular(destination).st_size != intent.size or _digest(destination) != intent.sha256:
        raise LabError('published verification failed')
    return {'state': 'NEW_VERIFIED_COPY', 'bytes': intent.size,
            'new_transfer': True, 'direction': intent.direction,
            'rsync_stats': stdout[-1500:]}
