"""Verified, resumable, never-clobbering file operations.

``copy_file``
    Streams into a hidden partial file named for the exact source version,
    fsyncs, stamps the source mtime, drops the page cache and reads the copy
    back to compare SHA-256, then publishes it. New files are published with
    ``renameat2(RENAME_NOREPLACE)`` so nothing that appears at the last instant
    is overwritten. An interrupted copy keeps its partial; the next run proves
    it is a byte-exact prefix of the unchanged source and continues from there.

``delete_file``
    Removes a USB file only if it is still exactly the version the plan saw,
    then prunes folders the deletion left empty.

``retire_file``
    Moves a NAS file into the drive's ``.loadmaster-replaced`` folder instead
    of deleting or overwriting it. Same-filesystem rename only.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import stat
import threading
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .scan import Fingerprint

PARTIAL_SUFFIX = ".loadmaster-partial"
CHUNK = 8 * 1024 * 1024


class ItemError(RuntimeError):
    """This one file could not be handled; the run continues."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


class Cancelled(RuntimeError):
    """The run was asked to stop. Partial files are kept for resume."""


# Errors that mean the device or filesystem is unusable: stop the whole run.
FATAL_ERRNOS = frozenset(
    {errno.ENOSPC, errno.EIO, errno.EROFS, errno.ENODEV, errno.ENXIO, errno.EDQUOT}
)


@dataclass(frozen=True)
class CopyResult:
    sha256: str | None
    resumed_bytes: int


# --------------------------------------------------------------- helpers


def safe_relative(path: str) -> PurePosixPath:
    rel = PurePosixPath(path)
    if (
        not path
        or rel.is_absolute()
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        raise ItemError("UNSAFE_PATH", path)
    return rel


def ensure_parent(root: Path, rel: PurePosixPath, *, owner=None, mode=None) -> Path:
    """Create missing folders under ``root``; refuse symlinked or odd parents."""

    current = root
    for part in rel.parent.parts:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            os.mkdir(current, 0o755 if mode is None else mode)
            if owner is not None:
                os.chown(current, *owner, follow_symlinks=False)
            continue
        if not stat.S_ISDIR(info.st_mode):
            raise ItemError("BAD_PARENT", str(current))
    return current


def _fsync_dir(path: Path) -> None:
    with suppress(OSError):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        except OSError:
            pass  # exFAT/vfat may refuse directory fsync
        finally:
            os.close(fd)


def _drop_cache(fd: int) -> None:
    with suppress(AttributeError, OSError):
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)


_renameat2 = None


def _noreplace_rename(source: Path, target: Path) -> None:
    """Atomic rename that fails if ``target`` exists."""

    global _renameat2
    if _renameat2 is None:
        try:
            func = ctypes.CDLL(None, use_errno=True).renameat2
            func.argtypes = (
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            )
            func.restype = ctypes.c_int
            _renameat2 = func
        except (AttributeError, OSError):
            _renameat2 = False

    if _renameat2:
        at_fdcwd, rename_noreplace = -100, 1
        if (
            _renameat2(
                at_fdcwd,
                os.fsencode(source),
                at_fdcwd,
                os.fsencode(target),
                rename_noreplace,
            )
            == 0
        ):
            return
        err = ctypes.get_errno()
        if err == errno.EEXIST:
            raise ItemError("DESTINATION_APPEARED", str(target))
        if err not in {errno.EINVAL, errno.ENOSYS, errno.EOPNOTSUPP}:
            raise OSError(err, os.strerror(err), str(target))

    # Filesystem without RENAME_NOREPLACE: check, then rename.
    if os.path.lexists(target):
        raise ItemError("DESTINATION_APPEARED", str(target))
    os.rename(source, target)


def partial_path(parent: Path, rel: PurePosixPath, fp: Fingerprint) -> Path:
    key = hashlib.sha256(f"{rel}\n{fp.size}\n{fp.mtime_ns}".encode()).hexdigest()[:12]
    name = f".{rel.name}.{key}{PARTIAL_SUFFIX}"
    if len(os.fsencode(name)) > 240:
        name = f".{key}{PARTIAL_SUFFIX}"
    return parent / name


def _verified_prefix(
    partial: Path, source_fd: int, limit: int
) -> tuple[int, int, object]:
    """Return (offset, writable fd or -1, hasher) for a partial proven to be a prefix."""

    fresh = hashlib.sha256()
    try:
        size = partial.lstat().st_size
    except FileNotFoundError:
        return 0, -1, fresh
    if not 0 < size <= limit:
        partial.unlink()
        return 0, -1, fresh

    fd = os.open(partial, os.O_RDWR | os.O_NOFOLLOW)
    _drop_cache(fd)
    ours, theirs = hashlib.sha256(), hashlib.sha256()
    remaining = size
    while remaining:
        count = min(CHUNK, remaining)
        a, b = os.read(fd, count), os.read(source_fd, count)
        if len(a) != count or len(b) != count:
            break
        ours.update(a)
        theirs.update(b)
        remaining -= count
    if remaining or ours.digest() != theirs.digest():
        os.close(fd)
        partial.unlink()
        os.lseek(source_fd, 0, os.SEEK_SET)
        return 0, -1, fresh
    os.lseek(fd, size, os.SEEK_SET)
    return size, fd, theirs


# ------------------------------------------------------------------ copy


def copy_file(
    *,
    source: Path,
    dest_root: Path,
    rel: PurePosixPath,
    expected: Fingerprint,
    replace: bool,
    stop: threading.Event,
    verify: str = "sha256",
    owner: tuple[int, int] | None = None,
    before_publish: Callable[[Path], None] | None = None,
    on_bytes: Callable[[int], None] | None = None,
) -> CopyResult:
    """Copy ``source`` to ``dest_root/rel`` with verification.

    ``replace`` allows an existing destination to be replaced (planned
    updates); otherwise an existing destination fails the item.
    ``before_publish`` runs after verification and before the copy is put in
    place; the NAS side uses it to retire the old version.
    """

    parent = ensure_parent(dest_root, rel, owner=owner, mode=0o775 if owner else None)
    target = parent / rel.name
    partial = partial_path(parent, rel, expected)

    if os.path.lexists(target):
        if not stat.S_ISREG(target.lstat().st_mode):
            raise ItemError("DESTINATION_NOT_A_FILE", str(target))
        if not replace:
            raise ItemError("DESTINATION_APPEARED", str(target))

    try:
        src = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError as error:
        raise ItemError("SOURCE_GONE", str(source)) from error
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise ItemError("SOURCE_IS_SYMLINK", str(source)) from error
        raise

    try:
        info = os.fstat(src)
        if not stat.S_ISREG(info.st_mode) or not expected.same_as(
            Fingerprint(info.st_size, info.st_mtime_ns)
        ):
            raise ItemError("SOURCE_CHANGED", str(source))

        # Partials for other versions of this file are stale.
        prefix = f".{rel.name}."
        with suppress(OSError):
            for entry in os.scandir(parent):
                if (
                    entry.name.startswith(prefix)
                    and entry.name.endswith(PARTIAL_SUFFIX)
                    and entry.name != partial.name
                ):
                    os.unlink(entry.path)

        resumed, out, hasher = _verified_prefix(partial, src, info.st_size)
        if out < 0:
            out = os.open(
                partial,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o664 if owner else 0o644,
            )
        elif on_bytes:
            on_bytes(resumed)

        try:
            written = resumed
            while True:
                if stop.is_set():
                    raise Cancelled()
                block = os.read(src, CHUNK)
                if not block:
                    break
                hasher.update(block)
                view = memoryview(block)
                while view:
                    view = view[os.write(out, view) :]
                written += len(block)
                if on_bytes:
                    on_bytes(len(block))
            os.fsync(out)
        finally:
            os.close(out)

        after = os.stat(source, follow_symlinks=False)
        if written != info.st_size or (after.st_size, after.st_mtime_ns) != (
            info.st_size,
            info.st_mtime_ns,
        ):
            partial.unlink()
            raise ItemError("SOURCE_CHANGED_DURING_COPY", str(source))

        os.utime(partial, ns=(info.st_mtime_ns, info.st_mtime_ns))
        if owner is not None:
            os.chown(partial, *owner, follow_symlinks=False)

        source_hash = hasher.hexdigest()
        check = os.open(partial, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            _drop_cache(check)
            if os.fstat(check).st_size != info.st_size:
                raise ItemError("VERIFY_SIZE_MISMATCH", str(target))
            if verify == "sha256":
                readback = hashlib.sha256()
                while block := os.read(check, CHUNK):
                    if stop.is_set():
                        raise Cancelled()
                    readback.update(block)
                if readback.hexdigest() != source_hash:
                    partial.unlink()
                    raise ItemError("VERIFY_HASH_MISMATCH", str(target))
        finally:
            os.close(check)

        if before_publish is not None:
            before_publish(target)

        if replace and os.path.lexists(target):
            os.replace(partial, target)
        else:
            _noreplace_rename(partial, target)
        _fsync_dir(parent)
        return CopyResult(source_hash if verify == "sha256" else None, resumed)
    finally:
        os.close(src)


# ------------------------------------------------------- delete / retire


def _matches(path: Path, expected: Fingerprint) -> bool:
    info = path.lstat()
    return stat.S_ISREG(info.st_mode) and expected.same_as(
        Fingerprint(info.st_size, info.st_mtime_ns)
    )


def delete_file(root: Path, rel: PurePosixPath, expected: Fingerprint) -> None:
    target = root / rel
    try:
        if not _matches(target, expected):
            raise ItemError("CHANGED_SINCE_PLAN", str(target))
    except FileNotFoundError:
        return  # already gone
    os.unlink(target)
    parent = target.parent
    while parent != root and root in parent.parents:
        try:
            os.rmdir(parent)  # only succeeds when empty
        except OSError:
            break
        parent = parent.parent
    _fsync_dir(parent)


def retire_file(
    root: Path, rel: PurePosixPath, expected: Fingerprint | None, replaced_root: Path
) -> Path:
    """Move ``root/rel`` to ``replaced_root/rel``. Never deletes."""

    source = root / rel
    try:
        if expected is not None and not _matches(source, expected):
            raise ItemError("CHANGED_SINCE_PLAN", str(source))
    except FileNotFoundError as error:
        raise ItemError("SOURCE_GONE", str(source)) from error
    destination = replaced_root / rel
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        _noreplace_rename(source, destination)
    except OSError as error:
        if error.errno == errno.EXDEV:
            raise ItemError(
                "REPLACED_FOLDER_ON_OTHER_FILESYSTEM", str(source)
            ) from error
        raise
    return destination


__all__ = [
    "Cancelled",
    "CopyResult",
    "FATAL_ERRNOS",
    "ItemError",
    "PARTIAL_SUFFIX",
    "copy_file",
    "delete_file",
    "retire_file",
    "safe_relative",
]
