"""Fail-closed Loadmaster backup preflight.

This module does not perform physical transfers.
Hardware evidence must be obtained independently at execution time.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path


class BackupExecutionError(RuntimeError):
    """A required transfer safety condition was not satisfied."""


@dataclass(frozen=True)
class BackupPreflight:
    source_root: Path
    destination_root: Path
    relative_path: str
    expected_size: int
    registered_uuid: str
    observed_uuid: str
    allow_backup: bool
    mount_writable: bool
    physical_confirmation: bool


def _reject_symlink_chain(path: Path) -> None:
    for component in (path, *path.parents):
        if component.is_symlink():
            raise BackupExecutionError(
                f"symlink in transfer path: {component}"
            )


def validate_backup_preflight(request: BackupPreflight) -> dict:
    """Validate one proposed NAS-to-USB action without writing."""

    if request.allow_backup is not True:
        raise BackupExecutionError("backup authorization disabled")

    if (
        not request.registered_uuid
        or not request.observed_uuid
        or request.registered_uuid != request.observed_uuid
    ):
        raise BackupExecutionError("cartridge identity mismatch")

    if request.mount_writable is not True:
        raise BackupExecutionError("destination mount not writable")

    if request.physical_confirmation is not True:
        raise BackupExecutionError("physical confirmation required")

    relative = Path(request.relative_path)

    if (
        not request.relative_path
        or relative.is_absolute()
        or ".." in relative.parts
        or "." in relative.parts
        or str(relative) != request.relative_path
    ):
        raise BackupExecutionError("unsafe relative path")

    if (
        not request.source_root.is_absolute()
        or not request.destination_root.is_absolute()
    ):
        raise BackupExecutionError("transfer roots must be absolute")

    if (
        isinstance(request.expected_size, bool)
        or not isinstance(request.expected_size, int)
        or request.expected_size < 0
    ):
        raise BackupExecutionError("invalid expected size")

    source = request.source_root / relative
    destination = request.destination_root / relative

    _reject_symlink_chain(source)
    _reject_symlink_chain(destination)

    try:
        info = source.lstat()
    except OSError as error:
        raise BackupExecutionError(
            f"source unavailable: {error}"
        ) from error

    if not stat.S_ISREG(info.st_mode):
        raise BackupExecutionError("source is not a regular file")

    if info.st_size != request.expected_size:
        raise BackupExecutionError("source size changed")

    if not request.destination_root.is_dir():
        raise BackupExecutionError("destination root unavailable")

    # lexists includes dangling symlinks.
    if os.path.lexists(destination):
        raise BackupExecutionError("destination already exists")

    return {
        "state": "PREFLIGHT_READY",
        "direction": "NAS_TO_USB",
        "source": str(source),
        "destination": str(destination),
        "size_bytes": info.st_size,
        "read_only": True,
        "executed": False,
    }


def copy_disposable_test_file(
    source: Path,
    destination: Path,
    *,
    interrupt_after_bytes: int | None = None,
) -> dict:
    """Prototype only: verified copying within a disposable test tree.

    NOT a production cartridge executor. Caller-provided paths are not
    sufficient authorization for physical USB transfers.
    """
    import hashlib
    import tempfile

    if not source.is_file() or source.is_symlink():
        raise BackupExecutionError("invalid test source")

    if destination.exists() or destination.is_symlink():
        raise BackupExecutionError("destination already exists")

    if not destination.parent.is_dir():
        raise BackupExecutionError("test destination parent missing")

    temporary = None
    original_hash = hashlib.sha256()
    bytes_written = 0

    try:
        fd, name = tempfile.mkstemp(
            prefix=".loadmaster-test-",
            dir=destination.parent,
        )
        temporary = Path(name)

        with source.open("rb") as reader, os.fdopen(fd, "wb") as writer:
            while chunk := reader.read(1024 * 1024):
                original_hash.update(chunk)
                writer.write(chunk)
                bytes_written += len(chunk)

                if (
                    interrupt_after_bytes is not None
                    and bytes_written >= interrupt_after_bytes
                ):
                    raise BackupExecutionError("simulated interruption")

            writer.flush()
            os.fsync(writer.fileno())

        verified_hash = hashlib.sha256()

        with temporary.open("rb") as reader:
            while chunk := reader.read(1024 * 1024):
                verified_hash.update(chunk)

        if original_hash.digest() != verified_hash.digest():
            raise BackupExecutionError("checksum mismatch")

        # Hard-link publication fails if the destination already exists.
        # Unlike os.replace(), this cannot overwrite a previous backup.
        os.link(temporary, destination)
        os.unlink(temporary)
        temporary = None

        return {
            "state": "VERIFIED_TEST_COPY",
            "size_bytes": bytes_written,
            "sha256": verified_hash.hexdigest(),
        }

    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)



def publish_noreplace(
    temporary_name: str,
    destination_name: str,
    directory: Path,
) -> None:
    """Publish within one directory without replacing existing files.

    Requires Linux renameat2(RENAME_NOREPLACE).
    This is a primitive, not physical-transfer authorization.
    """
    import ctypes

    for name in (temporary_name, destination_name):
        if (
            not name
            or name in (".", "..")
            or "/" in name
            or "\\x00" in name
        ):
            raise BackupExecutionError("invalid publication filename")

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(directory, flags)

    try:
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = libc.renameat2
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int

        RENAME_NOREPLACE = 1

        result = renameat2(
            fd,
            os.fsencode(temporary_name),
            fd,
            os.fsencode(destination_name),
            RENAME_NOREPLACE,
        )

        if result != 0:
            error = ctypes.get_errno()
            raise BackupExecutionError(
                f"atomic publication refused: "
                f"{os.strerror(error)} (errno={error})"
            )

        os.fsync(fd)

    finally:
        os.close(fd)



def execute_sandbox_backup(
    request: BackupPreflight,
    *,
    sandbox_root: Path,
    fault: str | None = None,
) -> dict:
    """Integrated test-only executor confined to one temporary sandbox.

    Not suitable for hardware use. Authorization is simulated.
    """
    import hashlib
    import tempfile

    if fault not in (None, "interrupt", "corrupt", "source_change",
                     "destination_race"):
        raise BackupExecutionError("unknown test fault")

    sandbox = sandbox_root.resolve(strict=True)
    if not sandbox.is_dir() or sandbox.is_symlink():
        raise BackupExecutionError("invalid test sandbox")

    for root in (request.source_root, request.destination_root):
        if root.is_symlink() or not root.is_dir():
            raise BackupExecutionError("invalid test root")
        resolved = root.resolve(strict=True)
        if resolved == sandbox or sandbox not in resolved.parents:
            raise BackupExecutionError("transfer root outside sandbox")

    result = validate_backup_preflight(request)
    source = Path(result["source"])
    destination = Path(result["destination"])

    # This test implementation supports an existing destination directory.
    # Directory creation and race-safe path walking come later.
    if not destination.parent.is_dir():
        raise BackupExecutionError("destination parent missing")

    _reject_symlink_chain(destination.parent)

    temporary = None
    size = 0
    source_hash = hashlib.sha256()

    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW
        source_fd = os.open(source, flags)
        try:
            before = os.fstat(source_fd)

            if not stat.S_ISREG(before.st_mode):
                raise BackupExecutionError("source not regular")
            if before.st_size != request.expected_size:
                raise BackupExecutionError("source size changed")

            fd, name = tempfile.mkstemp(
                prefix=".loadmaster-sandbox-",
                dir=destination.parent,
            )
            temporary = Path(name)

            with os.fdopen(fd, "wb") as writer:
                with os.fdopen(os.dup(source_fd), "rb") as reader:
                    while chunk := reader.read(1024 * 1024):
                        writer.write(chunk)
                        source_hash.update(chunk)
                        size += len(chunk)

                        if fault == "interrupt":
                            raise BackupExecutionError(
                                "simulated interruption"
                            )

                writer.flush()
                os.fsync(writer.fileno())

            after = os.fstat(source_fd)

            if fault == "source_change":
                raise BackupExecutionError(
                    "simulated source mutation"
                )

            if (
                size != request.expected_size
                or before.st_dev != after.st_dev
                or before.st_ino != after.st_ino
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns
            ):
                raise BackupExecutionError(
                    "source changed during transfer"
                )
        finally:
            os.close(source_fd)

        if fault == "corrupt":
            with temporary.open("r+b") as writer:
                writer.seek(0)
                writer.write(b"X")
                writer.flush()
                os.fsync(writer.fileno())

        verified = hashlib.sha256()
        with temporary.open("rb") as reader:
            while chunk := reader.read(1024 * 1024):
                verified.update(chunk)

        if verified.digest() != source_hash.digest():
            raise BackupExecutionError("checksum mismatch")

        if fault == "destination_race":
            destination.write_bytes(b"other writer")

        publish_noreplace(
            temporary.name,
            destination.name,
            destination.parent,
        )
        temporary = None

        return {
            "state": "VERIFIED_SANDBOX_COPY",
            "size_bytes": size,
            "sha256": verified.hexdigest(),
            "executed": True,
        }

    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
