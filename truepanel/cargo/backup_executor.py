"""Fail-closed Loadmaster backup preflight.

This module does not perform physical transfers.
Hardware evidence must be obtained independently at execution time.
"""

from __future__ import annotations

import os
import stat
import threading
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



class SingleUseTransferAuthority:
    """Process-local, single-use confirmation validation.

    Development-stage authorization component. Not a persistent or
    independently authenticated physical hardware boundary.
    """

    def __init__(self, *, clock, max_age_seconds=30.0):
        self._clock = clock
        self._max_age = float(max_age_seconds)
        self._consumed = set()
        self._lock = threading.Lock()

        if self._max_age <= 0:
            raise ValueError("confirmation lifetime must be positive")

    def consume(
        self,
        confirmation,
        *,
        cartridge_id: str,
        cartridge_uuid: str,
        device_serial: str,
        plan_digest: str,
    ) -> None:
        from .copy_button import CopyButtonConfirmation

        if type(confirmation) is not CopyButtonConfirmation:
            raise BackupExecutionError(
                "untrusted confirmation type"
            )

        expected = (
            cartridge_id,
            cartridge_uuid,
            device_serial,
            plan_digest,
        )

        actual = (
            confirmation.cartridge_id,
            confirmation.cartridge_uuid,
            confirmation.device_serial,
            confirmation.plan_digest,
        )

        if not all(expected) or actual != expected:
            raise BackupExecutionError(
                "confirmation does not match approved transfer"
            )

        now = float(self._clock())
        age = now - confirmation.confirmed_at_monotonic

        if age < 0 or age > self._max_age:
            raise BackupExecutionError(
                "physical confirmation expired"
            )

        with self._lock:
            if plan_digest in self._consumed:
                raise BackupExecutionError(
                    "physical confirmation already consumed"
                )
            self._consumed.add(plan_digest)


class HostConfirmationHandoff:
    """In-process, non-actuating bridge for the host GPIO callback.

    The host owns this object and passes `on_confirmation` only to its
    LoadmasterCopyButtonService instance. It refuses a second callback,
    consumption, or arm for the same plan. This is intentionally not a
    cross-process or durable authorization mechanism.
    """

    def __init__(self, *, clock, max_age_seconds=30.0):
        self._authority = SingleUseTransferAuthority(
            clock=clock, max_age_seconds=max_age_seconds
        )
        self._lock = threading.Lock()
        self._expected = None
        self._received = None
        self._used = False

    def arm(self, *, cartridge_id, cartridge_uuid, device_serial, plan_digest):
        expected = (cartridge_id, cartridge_uuid, device_serial, plan_digest)
        if not all(isinstance(x, str) and x for x in expected):
            raise BackupExecutionError("incomplete host authorization context")
        with self._lock:
            if self._expected is not None:
                raise BackupExecutionError("handoff already armed or consumed")
            self._expected = expected

    def on_confirmation(self, confirmation):
        """Callback intended for host service; never executes a transfer."""
        from .copy_button import CopyButtonConfirmation
        with self._lock:
            if self._expected is None or self._received is not None or self._used:
                raise BackupExecutionError("handoff not waiting for confirmation")
            if type(confirmation) is not CopyButtonConfirmation:
                raise BackupExecutionError("invalid confirmation object")
            self._received = confirmation

    def consume(self):
        """Validate callback evidence once; returns no copy authority token."""
        with self._lock:
            if self._used or self._received is None or self._expected is None:
                raise BackupExecutionError("no unused host confirmation")
            self._used = True  # fail closed even if validation raises
            cartridge_id, cartridge_uuid, device_serial, plan_digest = self._expected
            self._authority.consume(
                self._received,
                cartridge_id=cartridge_id,
                cartridge_uuid=cartridge_uuid,
                device_serial=device_serial,
                plan_digest=plan_digest,
            )
            return {"state": "HOST_CONFIRMATION_CONSUMED", "executed": False}

    def disarm(self):
        with self._lock:
            self._used = True
            self._received = None


def build_verified_sandbox_manifest(*, source: Path, copy_result: dict) -> dict:
    """Prepare manifest evidence only from an already verified sandbox copy.

    Caller must persist through existing manifest writer. This method never
    claims a physical cartridge backup.
    """
    from datetime import datetime, timezone
    if (copy_result.get("state") != "VERIFIED_SANDBOX_COPY"
            or copy_result.get("executed") is not True):
        raise BackupExecutionError("copy is not verified")
    digest = copy_result.get("sha256")
    size = copy_result.get("size_bytes")
    if (not isinstance(digest, str) or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
            or type(size) is not int or size < 0
            or not source.is_absolute()):
        raise BackupExecutionError("invalid verification evidence")
    stamp = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": 1,
        "kind": "truepanel.cargo_backup_manifest",
        "created_at": stamp,
        "source": "loadmaster-sandbox-verification-only",
        "items": [{"path": str(source), "size_bytes": size,
                   "backed_up_at": stamp, "sha256": digest}],
    }


def execute_physical_backup(*args, **kwargs):
    """Hard stop: cannot perform hardware writes from development package."""
    raise BackupExecutionError(
        "physical executor not enabled: hardware attestation, persistent "
        "authorization, and exFAT no-replace validation incomplete"
    )


@dataclass(frozen=True)
class HardwareAttestation:
    """Observed, read-only physical device identity (never write authority)."""
    mount: str
    device: str
    filesystem: str
    uuid: str
    by_id: str
    read_only: bool
    matches_registry: bool


def attest_cartridge_read_only(
    *, mount: Path, registered_uuid: str, registered_by_id: str,
    command_runner=None,
) -> HardwareAttestation:
    """Independently inspect mount, UUID and hardware by-id link.

    This explicitly refuses writable mounts and cannot authorize execution.
    Require a pinned /dev/disk/by-id/*-partN identity; generic udev serials
    are not accepted. The command_runner injection is for unit tests only.
    """
    import subprocess
    from pathlib import PurePosixPath

    if command_runner is None:
        def command_runner(args):
            return subprocess.check_output(args, text=True, timeout=10)

    if (not mount.is_absolute() or '..' in mount.parts or mount.is_symlink()
            or not registered_uuid or not registered_by_id.startswith('/dev/disk/by-id/')
            or '..' in PurePosixPath(registered_by_id).parts
            or PurePosixPath(registered_by_id).name in ('', '.', '..')):
        raise BackupExecutionError('invalid attestation input')

    try:
        # -M means an exact mount, never an enclosing parent filesystem.
        info = command_runner([
            'findmnt', '-n', '-M', str(mount), '-o',
            'SOURCE,TARGET,FSTYPE,OPTIONS', '--raw',
        ]).strip().split(None, 3)
        if len(info) != 4:
            raise BackupExecutionError('mount not uniquely identified')
        device, target, filesystem, options = info
        if target != str(mount) or not device.startswith('/dev/'):
            raise BackupExecutionError('unexpected mount target or source')
        opts = set(options.split(','))
        if 'ro' not in opts or 'rw' in opts:
            raise BackupExecutionError('mount not read-only')
        if filesystem.lower() != 'exfat':
            raise BackupExecutionError('unexpected cartridge filesystem')
        observed_uuid = command_runner([
            'blkid', '-s', 'UUID', '-o', 'value', device,
        ]).strip()
        observed_fs = command_runner([
            'blkid', '-s', 'TYPE', '-o', 'value', device,
        ]).strip()
        # Realpath is applied to the by-id link *and* mounted source.
        mounted_realpath = command_runner(['readlink', '-f', device]).strip()
        by_id_realpath = command_runner([
            'readlink', '-f', registered_by_id,
        ]).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise BackupExecutionError('cartridge observation failed') from error

    if (observed_uuid != registered_uuid or observed_fs.lower() != 'exfat'
            or not mounted_realpath or mounted_realpath != by_id_realpath):
        raise BackupExecutionError('physical cartridge identity mismatch')
    return HardwareAttestation(
        mount=str(mount), device=device, filesystem=filesystem,
        uuid=observed_uuid, by_id=registered_by_id, read_only=True,
        matches_registry=True,
    )


class DurableConfirmationJournal:
    """Fail-closed, crash-persistent plan consumption on a trusted local disk.

    A digest is burned before any physical action. Journal state is not a
    GPIO provenance guarantee. The caller must own and protect this directory.
    """

    def __init__(self, directory: Path):
        if not directory.is_absolute() or directory.is_symlink():
            raise BackupExecutionError('unsafe journal directory')
        self.directory = directory
        self._lock = threading.Lock()

    def consume(self, *, cartridge_id: str, plan_digest: str) -> Path:
        import hashlib
        import json
        import re
        if (not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', cartridge_id)
                or not re.fullmatch(r'[a-fA-F0-9]{64}', plan_digest)):
            raise BackupExecutionError('invalid confirmation identity')
        if not self.directory.is_dir() or self.directory.is_symlink():
            raise BackupExecutionError('journal directory unavailable')
        if self.directory.stat().st_mode & 0o022:
            raise BackupExecutionError('journal directory is writable by others')
        digest = hashlib.sha256((cartridge_id + ':' + plan_digest.lower()).encode()).hexdigest()
        path = self.directory / (digest + '.consumed')
        with self._lock:
            fd = None
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'w') as f:
                    fd = None
                    json.dump({'cartridge_id': cartridge_id, 'plan_digest': plan_digest.lower(),
                               'status': 'CONSUMED_BEFORE_TRANSFER'}, f)
                    f.write('\n')
                    f.flush()
                    os.fsync(f.fileno())
                parent_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(parent_fd)
                finally:
                    os.close(parent_fd)
            except FileExistsError as error:
                raise BackupExecutionError('physical authorization already consumed') from error
            except OSError as error:
                # If a record was created before an I/O failure, leave it
                # in place to avoid accidentally re-authorizing on retry.
                raise BackupExecutionError('durable authorization recording failed') from error
            finally:
                if fd is not None:
                    os.close(fd)
        return path
