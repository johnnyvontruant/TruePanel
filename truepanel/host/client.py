"""Read-only application client for Host Agent published status."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from truepanel.hardware.fan_status_bridge import (
    DEFAULT_FAN_CONTROL_STATUS_PATH,
    FanControlStatusBridge,
)


class HostAgentStatusClient:
    """Read Host fan/thermal status without owning or commanding hardware."""

    def __init__(
        self,
        *,
        path: str | Path = DEFAULT_FAN_CONTROL_STATUS_PATH,
        reader: Callable[..., dict[str, Any] | None] | None = None,
    ) -> None:
        self.status_path = Path(path)
        self._reader = (
            reader
            if reader is not None
            else FanControlStatusBridge(
                self.status_path
            ).read
        )

    def read_fan_status(
        self,
        *,
        max_age: float = 30.0,
    ) -> dict[str, Any] | None:
        """Return the latest fresh Host-published status snapshot."""

        return self._reader(
            max_age=max_age
        )


__all__ = [
    "HostAgentStatusClient",
]
