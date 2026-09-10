"""Operator-owned OpenSSH signature verification for AEGIS review receipts.

Only public trust material enters this adapter.  Private keys and signing stay
outside TruePanel, and verification never grants promotion authority.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import Final

DEFAULT_NAMESPACE: Final = "truepanel-aegis-review-v1@truepanel"
MAX_ALLOWED_SIGNERS_BYTES: Final = 64 * 1024
MAX_SIGNATURE_BYTES: Final = 32 * 1024


class OpenSshSignatureVerifier:
    """Verify SSHSIG receipts against a protected allowed-signers snapshot."""

    def __init__(
        self,
        allowed_signers_path: str | Path,
        *,
        namespace: str = DEFAULT_NAMESPACE,
        executable: str = "/usr/bin/ssh-keygen",
        timeout: float = 5.0,
    ) -> None:
        self.allowed_signers_path = Path(allowed_signers_path)
        self.namespace = namespace
        self.executable = executable
        self.timeout = float(timeout)

    @staticmethod
    def _snapshot(path: Path, *, maximum: int) -> bytes:
        if not path.is_absolute() or not hasattr(os, "O_NOFOLLOW"):
            raise ValueError("ProtectedFileUnavailable")
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("ProtectedFileNotRegular")
            if before.st_uid != os.geteuid() or before.st_mode & 0o022:
                raise ValueError("ProtectedFilePermissionsInvalid")
            if before.st_size <= 0 or before.st_size > maximum:
                raise ValueError("ProtectedFileSizeInvalid")
            chunks: list[bytes] = []
            remaining = maximum + 1
            while remaining:
                chunk = os.read(descriptor, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            after = os.fstat(descriptor)
            def identity(value: os.stat_result) -> tuple[int, ...]:
                return (
                    value.st_dev,
                    value.st_ino,
                    value.st_mode,
                    value.st_uid,
                    value.st_size,
                    value.st_mtime_ns,
                    value.st_ctime_ns,
                )
            if identity(before) != identity(after):
                raise ValueError("ProtectedFileChanged")
            if not payload or len(payload) > maximum:
                raise ValueError("ProtectedFileSizeInvalid")
            return payload
        finally:
            os.close(descriptor)

    @staticmethod
    def _memfd(name: str, payload: bytes) -> int:
        if not hasattr(os, "memfd_create") or not hasattr(os, "MFD_CLOEXEC"):
            raise ValueError("MemoryFileUnavailable")
        descriptor = os.memfd_create(name, flags=os.MFD_CLOEXEC)
        try:
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise ValueError("MemoryFileWriteFailed")
                view = view[written:]
            os.lseek(descriptor, 0, os.SEEK_SET)
            return descriptor
        except Exception:
            os.close(descriptor)
            raise

    def __call__(self, key_id: str, statement: bytes, signature: str) -> bool:
        """Return false for every malformed, unavailable, or rejected input."""

        if (
            not key_id
            or any(character.isspace() for character in key_id)
            or not self.namespace
            or not Path(self.executable).is_absolute()
            or not isinstance(statement, bytes)
            or not statement
            or not isinstance(signature, str)
        ):
            return False
        try:
            encoded_signature = signature.encode("ascii")
        except UnicodeEncodeError:
            return False
        if not encoded_signature or len(encoded_signature) > MAX_SIGNATURE_BYTES:
            return False

        descriptors: list[int] = []
        try:
            allowed = self._snapshot(
                self.allowed_signers_path, maximum=MAX_ALLOWED_SIGNERS_BYTES
            )
            allowed_fd = self._memfd("truepanel-allowed-signers", allowed)
            signature_fd = self._memfd("truepanel-review-signature", encoded_signature)
            descriptors.extend((allowed_fd, signature_fd))
            result = subprocess.run(
                [
                    self.executable,
                    "-Y",
                    "verify",
                    "-f",
                    f"/proc/self/fd/{allowed_fd}",
                    "-I",
                    key_id,
                    "-n",
                    self.namespace,
                    "-s",
                    f"/proc/self/fd/{signature_fd}",
                ],
                input=statement,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self.timeout,
                check=False,
                pass_fds=(allowed_fd, signature_fd),
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError, ValueError):
            return False
        finally:
            for descriptor in descriptors:
                os.close(descriptor)


__all__ = ["DEFAULT_NAMESPACE", "OpenSshSignatureVerifier"]
