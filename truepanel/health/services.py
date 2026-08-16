"""Read-only runtime service status for Health Intelligence."""

from __future__ import annotations

import subprocess
import time
from typing import Callable


REQUIRED_SERVICES = (
    "truepanel.service",
    "truepanel-mission-control.service",
)


class ServiceStatusProvider:
    """Observe required TruePanel systemd units with a short-lived cache."""

    def __init__(
        self,
        *,
        runner: Callable = subprocess.run,
        clock: Callable[[], float] = time.monotonic,
        cache_seconds: float = 5.0,
    ):
        self.runner = runner
        self.clock = clock
        self.cache_seconds = float(cache_seconds)

        self._cached_at: float | None = None
        self._cached_payload: dict | None = None

    def snapshot(self) -> dict:
        now = float(self.clock())

        if (
            self._cached_at is not None
            and self._cached_payload is not None
            and now - self._cached_at < self.cache_seconds
        ):
            return dict(self._cached_payload)

        payload = {
            "available": True,
            "services": [
                self._service_status(name)
                for name in REQUIRED_SERVICES
            ],
        }

        payload["available"] = any(
            item.get("observed")
            for item in payload["services"]
        )

        self._cached_at = now
        self._cached_payload = payload

        return dict(payload)

    def _service_status(self, name: str) -> dict:
        command = [
            "systemctl",
            "show",
            name,
            "--property=LoadState",
            "--property=ActiveState",
            "--property=SubState",
        ]

        try:
            result = self.runner(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return {
                "name": name,
                "required": True,
                "observed": False,
                "load_state": "unavailable",
                "active_state": "unavailable",
                "sub_state": "unavailable",
            }

        properties = {}

        for line in result.stdout.splitlines():
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            properties[key] = value

        observed = all(
            key in properties
            for key in (
                "LoadState",
                "ActiveState",
                "SubState",
            )
        )

        return {
            "name": name,
            "required": True,
            "observed": observed,
            "load_state": properties.get(
                "LoadState",
                "unknown",
            ),
            "active_state": properties.get(
                "ActiveState",
                "unknown",
            ),
            "sub_state": properties.get(
                "SubState",
                "unknown",
            ),
        }


__all__ = [
    "REQUIRED_SERVICES",
    "ServiceStatusProvider",
]
