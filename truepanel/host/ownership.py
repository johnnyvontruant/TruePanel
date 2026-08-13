"""Cross-process single-owner interlock for privileged Host hardware."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import TextIO

DEFAULT_HOST_OWNERSHIP_PATH = Path(
    "/run/truepanel/host-owner.lock"
)


class HostOwnershipError(RuntimeError):
    """Raised when another process already owns Host hardware."""


class HostOwnershipGuard:
    """Hold one non-blocking process lease for Host hardware ownership."""

    def __init__(
        self,
        owner_name: str,
        *,
        path: str | Path = DEFAULT_HOST_OWNERSHIP_PATH,
    ) -> None:
        owner_name = str(owner_name).strip()
        if not owner_name:
            raise ValueError(
                "Host ownership name must not be empty"
            )

        self.owner_name = owner_name
        self.path = Path(path)
        self._handle: TextIO | None = None

    @property
    def held(self) -> bool:
        """Return whether this guard currently owns the lease."""

        return self._handle is not None

    def acquire(self) -> None:
        """Acquire exclusive Host ownership without waiting."""

        if self._handle is not None:
            return

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o755,
        )

        handle = self.path.open(
            "a+",
            encoding="utf-8",
        )

        try:
            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError as error:
            handle.seek(0)
            occupant = handle.read().strip()
            handle.close()

            detail = (
                f" Current owner: {occupant}."
                if occupant
                else ""
            )
            raise HostOwnershipError(
                "Host hardware ownership is already held."
                + detail
            ) from error

        try:
            handle.seek(0)
            handle.truncate()
            json.dump(
                {
                    "owner": self.owner_name,
                    "pid": os.getpid(),
                },
                handle,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        except Exception:
            try:
                fcntl.flock(
                    handle.fileno(),
                    fcntl.LOCK_UN,
                )
            finally:
                handle.close()
            raise

        self._handle = handle

    def release(self) -> None:
        """Release Host ownership. The lock inode is never unlinked."""

        handle = self._handle
        if handle is None:
            return

        self._handle = None
        try:
            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_UN,
            )
        finally:
            handle.close()


__all__ = [
    "DEFAULT_HOST_OWNERSHIP_PATH",
    "HostOwnershipError",
    "HostOwnershipGuard",
]
