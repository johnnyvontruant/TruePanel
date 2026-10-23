"""Verified Loadmaster transfer executor.

This is the only Loadmaster component that writes media. It runs exactly one
confirmed run plan and nothing else:

1. **Re-plan and seal.** The plan is rebuilt from live disk state; the run is
   refused unless the fresh plan is ``READY`` and its digest equals the digest
   the physical Copy press confirmed. Anything that changed in between (a new
   import, a modified file, a different cartridge) aborts with no writes.
2. **Capacity.** Each destination must have room for its bytes plus a margin.
3. **Copy per file, crash-safe.** Each file streams into a hidden
   ``.<name>.loadmaster-partial`` sibling (``O_EXCL``/``O_NOFOLLOW``), is
   hashed while copying, ``fsync``-ed, stamped with the source mtime, then read
   back from the device (page cache dropped first) and compared by SHA-256.
   Only a verified copy is atomically renamed into place. A crash leaves at
   most one partial file, which scanners ignore and the next run replaces.
4. **Never delete, never clobber.** New files require an empty destination;
   overwrites happen only for planned update reasons. No source is modified.
5. **Evidence.** Verified NAS->USB copies are merged into the Cargo backup
   manifest (so the durable backlog clears on the observer's next pass), the
   cartridge inventory baseline is advanced, and a JSON receipt of every file
   is written. The receipt directory is Loadmaster's transfer log.

Per-file problems (a source changed mid-run) fail that file and continue.
Device-level problems (no space, I/O error, read-only filesystem, device gone)
stop the run immediately.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import os
import stat
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .backup_manifest import (
    CARGO_BACKUP_MANIFEST_KIND,
    CARGO_BACKUP_MANIFEST_SCHEMA_VERSION,
    validate_backup_manifest,
)
from .backup_producer import BackupProducerError, write_manifest_atomic
from .cartridges import CartridgeDefinition
from .loadmaster import (
    LOADMASTER_PARTIAL_SUFFIX,
    FileFingerprint,
    LoadmasterPlanError,
    inventory_payload,
)
from .run_plan import UPDATE_REASONS, RunAction, actions_from_plan, build_run_plan

LOADMASTER_RECEIPT_SCHEMA_VERSION = 1
LOADMASTER_RECEIPT_KIND = "truepanel.loadmaster_run_receipt"
MANIFEST_SOURCE = "truepanel.loadmaster"

DEFAULT_CHUNK_BYTES = 8 * 1024 * 1024
DEFAULT_FREE_SPACE_MARGIN_BYTES = 512 * 1024 * 1024

FATAL_ERRNOS = frozenset(
    {errno.ENOSPC, errno.EIO, errno.EROFS, errno.ENODEV, errno.ENXIO, errno.EDQUOT}
)

ProgressCallback = Callable[[dict[str, Any]], None]


class LoadmasterExecutionError(RuntimeError):
    """Run-level failure: nothing further is attempted."""


class _ItemError(RuntimeError):
    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


class _Cancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class ExecutorSettings:
    verify: str = "sha256"
    chunk_bytes: int = DEFAULT_CHUNK_BYTES
    free_space_margin_bytes: int = DEFAULT_FREE_SPACE_MARGIN_BYTES
    ingest_owner: tuple[int, int] | None = None
    ingest_file_mode: int = 0o664
    ingest_dir_mode: int = 0o775
    tolerance_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.verify not in {"sha256", "size"}:
            raise ValueError("Loadmaster verify must be 'sha256' or 'size'")
        if self.chunk_bytes <= 0:
            raise ValueError("Loadmaster chunk_bytes must be positive")


@dataclass
class RunContext:
    cartridge: CartridgeDefinition
    cartridges: list[CartridgeDefinition]
    usb_mount: Path
    backlog: dict[str, Any]
    inventory: dict[str, FileFingerprint]
    inventory_path: Path
    expected_digest: str
    ingest_enabled: bool
    receipts_dir: Path
    manifest_path: Path | None = None
    settings: ExecutorSettings = field(default_factory=ExecutorSettings)
    stop_event: threading.Event = field(default_factory=threading.Event)
    progress: ProgressCallback | None = None
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)


# --------------------------------------------------------------------- helpers


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _safe_relative(relative: str) -> PurePosixPath:
    path = PurePosixPath(relative)
    if (
        not relative
        or path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or any(part == "" for part in path.parts)
    ):
        raise _ItemError("UNSAFE_PATH", relative)
    return path


def _require_real_directory(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError as error:
        raise LoadmasterExecutionError(f"transfer root missing: {path}") from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise LoadmasterExecutionError(f"transfer root is not a real directory: {path}")


def _ensure_directory_chain(
    root: Path,
    relative_parent: PurePosixPath,
    *,
    mode: int | None,
    owner: tuple[int, int] | None,
) -> Path:
    current = root
    for part in relative_parent.parts:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            os.mkdir(current, mode if mode is not None else 0o755)
            if mode is not None:
                with suppress(OSError):
                    os.chmod(current, mode)
            if owner is not None:
                os.chown(current, owner[0], owner[1], follow_symlinks=False)
            continue
        if stat.S_ISLNK(info.st_mode):
            raise _ItemError("SYMLINK_IN_DESTINATION", str(current))
        if not stat.S_ISDIR(info.st_mode):
            raise _ItemError("NON_DIRECTORY_IN_DESTINATION", str(current))
    return current


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        # Some removable filesystems (exFAT/vfat) reject directory fsync.
        pass
    finally:
        os.close(fd)


def _free_bytes(path: Path) -> int:
    info = os.statvfs(path)
    return int(info.f_bavail) * int(info.f_frsize)


def _drop_cache(fd: int) -> None:
    advise = getattr(os, "posix_fadvise", None)
    if advise is None:
        return
    with suppress(OSError):
        advise(fd, 0, 0, os.POSIX_FADV_DONTNEED)


def _hash_fd(fd: int, chunk_bytes: int, stop: threading.Event) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        if stop.is_set():
            raise _Cancelled()
        block = os.read(fd, chunk_bytes)
        if not block:
            break
        digest.update(block)
        total += len(block)
    return digest.hexdigest(), total


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    lock_path = path.with_name(f".{path.name}.lock")
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        with suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


# ------------------------------------------------------------------ file copy


def copy_verified(
    *,
    source: Path,
    destination_root: Path,
    relative: PurePosixPath,
    expected_size: int,
    expected_mtime_ns: int,
    allow_replace: bool,
    settings: ExecutorSettings,
    stop: threading.Event,
    owner: tuple[int, int] | None = None,
    file_mode: int | None = None,
    dir_mode: int | None = None,
    on_bytes: Callable[[int], None] | None = None,
) -> str:
    """Copy one file into place only after verification. Returns its SHA-256."""

    parent = _ensure_directory_chain(
        destination_root, relative.parent, mode=dir_mode, owner=owner
    )
    destination = parent / relative.name
    partial = parent / f".{relative.name}{LOADMASTER_PARTIAL_SUFFIX}"

    try:
        existing = destination.lstat()
    except FileNotFoundError:
        existing = None

    if existing is not None:
        if not stat.S_ISREG(existing.st_mode):
            raise _ItemError("DESTINATION_NOT_REGULAR", str(destination))
        if not allow_replace:
            raise _ItemError("DESTINATION_APPEARED", str(destination))

    try:
        source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError as error:
        raise _ItemError("SOURCE_GONE", str(source)) from error
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise _ItemError("SOURCE_IS_SYMLINK", str(source)) from error
        raise

    try:
        info = os.fstat(source_fd)
        if not stat.S_ISREG(info.st_mode):
            raise _ItemError("SOURCE_NOT_REGULAR", str(source))
        if info.st_size != expected_size or info.st_mtime_ns != expected_mtime_ns:
            raise _ItemError("SOURCE_CHANGED", str(source))

        # A partial with our private suffix can only be a crashed earlier run.
        with suppress(FileNotFoundError):
            partial_info = partial.lstat()
            if not stat.S_ISREG(partial_info.st_mode):
                raise _ItemError("PARTIAL_NOT_REGULAR", str(partial))
            partial.unlink()

        partial_fd = os.open(
            partial,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o644,
        )
        try:
            digest = hashlib.sha256()
            written = 0
            while True:
                if stop.is_set():
                    raise _Cancelled()
                block = os.read(source_fd, settings.chunk_bytes)
                if not block:
                    break
                digest.update(block)
                view = memoryview(block)
                while view:
                    count = os.write(partial_fd, view)
                    view = view[count:]
                written += len(block)
                if on_bytes is not None:
                    on_bytes(len(block))
            os.fsync(partial_fd)
        finally:
            os.close(partial_fd)

        source_hash = digest.hexdigest()

        if written != expected_size:
            raise _ItemError("SHORT_READ", f"{written} != {expected_size}")

        after = os.stat(source, follow_symlinks=False)
        if after.st_size != expected_size or after.st_mtime_ns != expected_mtime_ns:
            raise _ItemError("SOURCE_CHANGED_DURING_COPY", str(source))

        os.utime(
            partial, ns=(expected_mtime_ns, expected_mtime_ns), follow_symlinks=False
        )

        if owner is not None:
            os.chown(partial, owner[0], owner[1], follow_symlinks=False)
        if file_mode is not None:
            with suppress(OSError):
                os.chmod(partial, file_mode)

        verify_fd = os.open(partial, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(verify_fd)
            _drop_cache(verify_fd)
            verify_info = os.fstat(verify_fd)
            if verify_info.st_size != expected_size:
                raise _ItemError("VERIFY_SIZE_MISMATCH", str(destination))
            if settings.verify == "sha256":
                readback_hash, readback_size = _hash_fd(
                    verify_fd, settings.chunk_bytes, stop
                )
                if readback_size != expected_size or readback_hash != source_hash:
                    raise _ItemError("VERIFY_HASH_MISMATCH", str(destination))
        finally:
            os.close(verify_fd)

        # Re-check right before publishing: a "new" destination must still be empty.
        if not allow_replace:
            try:
                destination.lstat()
            except FileNotFoundError:
                pass
            else:
                raise _ItemError("DESTINATION_APPEARED", str(destination))

        os.replace(partial, destination)
        _fsync_directory(parent)
        return source_hash

    except BaseException:
        with suppress(OSError):
            partial.unlink()
        raise

    finally:
        os.close(source_fd)


# --------------------------------------------------------------------- run


def _merge_manifest(
    manifest_path: Path,
    evidence: list[dict[str, Any]],
    *,
    now: datetime,
) -> None:
    with _locked(manifest_path):
        if manifest_path.exists():
            current = validate_backup_manifest(manifest_path)
            source = current["source"]
            items = {item["path"]: item for item in current["items"]}
        else:
            source = MANIFEST_SOURCE
            items = {}

        for item in evidence:
            items[item["path"]] = item

        write_manifest_atomic(
            manifest_path,
            {
                "schema_version": CARGO_BACKUP_MANIFEST_SCHEMA_VERSION,
                "kind": CARGO_BACKUP_MANIFEST_KIND,
                "created_at": _iso(now),
                "source": source,
                "items": [items[path] for path in sorted(items)],
            },
        )


def execute_run(context: RunContext) -> dict[str, Any]:
    """Execute one confirmed plan and return (and persist) its receipt."""

    started = context.clock()
    cartridge = context.cartridge
    receipt: dict[str, Any] = {
        "schema_version": LOADMASTER_RECEIPT_SCHEMA_VERSION,
        "kind": LOADMASTER_RECEIPT_KIND,
        "run_id": f"{started.strftime('%Y%m%dT%H%M%SZ')}-{cartridge.cartridge_id}",
        "cartridge": cartridge.public_dict(),
        "expected_digest": context.expected_digest,
        "started_at": _iso(started),
        "delete_policy": "never",
        "state": "RUNNING",
        "reason": None,
        "results": [],
    }

    try:
        _execute_into(context, receipt)
    except LoadmasterExecutionError as error:
        receipt["state"] = "FAILED"
        receipt["reason"] = str(error)
    except _Cancelled:
        receipt["state"] = "CANCELLED"
        receipt["reason"] = "stop requested"

    finished = context.clock()
    receipt["finished_at"] = _iso(finished)
    results = receipt["results"]
    receipt["summary"] = {
        "copied_files": sum(1 for r in results if r["outcome"] == "COPIED"),
        "copied_bytes": sum(
            r["size_bytes"] for r in results if r["outcome"] == "COPIED"
        ),
        "failed_files": sum(1 for r in results if r["outcome"] == "FAILED"),
        "skipped_files": sum(1 for r in results if r["outcome"] == "NOT_ATTEMPTED"),
    }

    _write_receipt(context.receipts_dir, receipt)
    return receipt


def _write_receipt(receipts_dir: Path, receipt: dict[str, Any]) -> None:
    try:
        receipts_dir.mkdir(parents=True, exist_ok=True)
        write_manifest_atomic(receipts_dir / f"{receipt['run_id']}.json", receipt)
        receipt["receipt_path"] = str(receipts_dir / f"{receipt['run_id']}.json")
    except (OSError, BackupProducerError) as error:
        receipt["receipt_error"] = str(error)


def _execute_into(context: RunContext, receipt: dict[str, Any]) -> None:
    cartridge = context.cartridge
    settings = context.settings

    try:
        plan = build_run_plan(
            cartridge=cartridge,
            cartridges=context.cartridges,
            usb_mount=context.usb_mount,
            backlog=context.backlog,
            inventory=context.inventory,
            ingest_enabled=context.ingest_enabled,
            tolerance_seconds=settings.tolerance_seconds,
        )
    except (LoadmasterPlanError, OSError) as error:
        raise LoadmasterExecutionError(f"re-plan failed: {error}") from error

    receipt["plan_digest"] = plan["digest"]
    receipt["plan_summary"] = plan["summary"]

    if plan["state"] != "READY":
        raise LoadmasterExecutionError(f"plan is {plan['state']}, not READY")

    if plan["digest"] != context.expected_digest:
        raise LoadmasterExecutionError(
            "plan changed since the Copy press was confirmed; nothing was copied"
        )

    nas_root = cartridge.source_prefix
    usb_root = context.usb_mount / cartridge.usb_relative_path
    _require_real_directory(nas_root)
    _require_real_directory(usb_root)

    actions = actions_from_plan(plan)

    needed = {
        "NAS_TO_USB": sum(a.size_bytes for a in actions if a.direction == "NAS_TO_USB"),
        "USB_TO_NAS": sum(a.size_bytes for a in actions if a.direction == "USB_TO_NAS"),
    }
    for direction, root in (("NAS_TO_USB", usb_root), ("USB_TO_NAS", nas_root)):
        if needed[direction] and (
            _free_bytes(root) < needed[direction] + settings.free_space_margin_bytes
        ):
            raise LoadmasterExecutionError(
                f"insufficient free space on {root} for {needed[direction]} bytes"
            )

    owner = settings.ingest_owner
    if owner is None:
        root_info = nas_root.lstat()
        owner = (root_info.st_uid, root_info.st_gid)
    can_chown = os.geteuid() == 0

    total_bytes = needed["NAS_TO_USB"] + needed["USB_TO_NAS"]
    progress = {
        "total_files": len(actions),
        "total_bytes": total_bytes,
        "done_files": 0,
        "done_bytes": 0,
        "current": None,
    }

    def report() -> None:
        if context.progress is not None:
            with suppress(Exception):
                context.progress(dict(progress))

    def on_bytes(count: int) -> None:
        progress["done_bytes"] += count
        report()

    results: list[dict[str, Any]] = receipt["results"]
    copied: list[tuple[RunAction, str]] = []
    fatal: str | None = None

    for action in actions:
        result = {
            "direction": action.direction,
            "relative_path": action.relative_path,
            "size_bytes": action.size_bytes,
            "reason": action.reason,
            "outcome": "NOT_ATTEMPTED",
            "sha256": None,
            "error": None,
        }
        results.append(result)

        if fatal is not None:
            continue

        progress["current"] = action.relative_path
        report()

        ingest = action.direction == "USB_TO_NAS"
        source_root, destination_root = (
            (usb_root, nas_root) if ingest else (nas_root, usb_root)
        )

        try:
            relative = _safe_relative(action.relative_path)
            sha = copy_verified(
                source=source_root / Path(*relative.parts),
                destination_root=destination_root,
                relative=relative,
                expected_size=action.size_bytes,
                expected_mtime_ns=action.source_mtime_ns,
                allow_replace=action.reason in UPDATE_REASONS,
                settings=settings,
                stop=context.stop_event,
                owner=owner if (ingest and can_chown) else None,
                file_mode=settings.ingest_file_mode if ingest else None,
                dir_mode=settings.ingest_dir_mode if ingest else None,
                on_bytes=on_bytes,
            )
        except _ItemError as error:
            result["outcome"] = "FAILED"
            result["error"] = str(error)
        except _Cancelled:
            result["outcome"] = "FAILED"
            result["error"] = "CANCELLED"
            fatal = "cancelled"
        except OSError as error:
            result["outcome"] = "FAILED"
            result["error"] = f"{type(error).__name__}: {error}"
            if error.errno in FATAL_ERRNOS:
                fatal = result["error"]
        else:
            result["outcome"] = "COPIED"
            result["sha256"] = sha
            copied.append((action, sha))

        progress["done_files"] += 1
        report()

    progress["current"] = None
    report()

    now = context.clock()
    _record_evidence(context, receipt, copied, now=now)

    if fatal is not None:
        receipt["state"] = "FAILED" if fatal != "cancelled" else "CANCELLED"
        receipt["reason"] = fatal
    elif any(r["outcome"] == "FAILED" for r in results):
        receipt["state"] = "PARTIAL"
    else:
        receipt["state"] = "COMPLETE"


def _record_evidence(
    context: RunContext,
    receipt: dict[str, Any],
    copied: list[tuple[RunAction, str]],
    *,
    now: datetime,
) -> None:
    if not copied:
        return

    cartridge = context.cartridge

    # Advance the conflict-detection baseline: both sides now match.
    inventory = dict(context.inventory)
    for action, _sha in copied:
        inventory[action.relative_path] = FileFingerprint(
            size_bytes=action.size_bytes, mtime_ns=action.source_mtime_ns
        )
    try:
        write_manifest_atomic(
            context.inventory_path,
            inventory_payload(
                cartridge=cartridge, files=inventory, captured_at=_iso(now)
            ),
        )
        receipt["inventory_updated"] = True
    except (OSError, BackupProducerError) as error:
        receipt["inventory_updated"] = False
        receipt["inventory_error"] = str(error)

    evidence = [
        {
            "path": str(cartridge.source_prefix / action.relative_path),
            "size_bytes": action.size_bytes,
            "backed_up_at": _iso(now),
            "sha256": sha,
        }
        for action, sha in copied
        if action.direction == "NAS_TO_USB"
    ]

    if not evidence or context.manifest_path is None:
        return

    try:
        _merge_manifest(context.manifest_path, evidence, now=now)
        receipt["manifest_updated"] = True
    except (OSError, ValueError, BackupProducerError) as error:
        receipt["manifest_updated"] = False
        receipt["manifest_error"] = str(error)


__all__ = [
    "ExecutorSettings",
    "LOADMASTER_RECEIPT_KIND",
    "LOADMASTER_RECEIPT_SCHEMA_VERSION",
    "LoadmasterExecutionError",
    "RunContext",
    "copy_verified",
    "execute_run",
]
