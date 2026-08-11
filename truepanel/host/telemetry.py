"""
Host-owned safety telemetry normalization.

This module owns the narrow telemetry contract consumed by privileged fan and
thermal safety logic. Physical collection remains injectable while the legacy
embedded runtime is migrated to the standalone Host Agent.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any


class HostFanTelemetryProvider:
    """
    Normalize the telemetry snapshot consumed by Host Agent safety services.

    The provider deliberately exposes only safety-relevant data:
    fan status, temperatures, and freshness.
    """

    def __init__(
        self,
        *,
        state_provider: Callable[
            [],
            Mapping[str, Any],
        ],
        fan_status_provider: Callable[
            [],
            Mapping[str, Any],
        ],
        clock: Callable[[], float] = time.time,
        freshness_seconds: float = 10.0,
    ) -> None:
        self._state_provider = state_provider
        self._fan_status_provider = (
            fan_status_provider
        )
        self._clock = clock
        self._freshness_seconds = float(
            freshness_seconds
        )

    @staticmethod
    def temperatures_from_state(
        state: Mapping[str, Any],
    ) -> tuple[float, ...]:
        """Normalize legacy collector temperatures."""

        temperatures_c: list[float] = []

        for item in (
            state.get(
                "temps",
                [],
            )
            or []
        ):
            if not isinstance(
                item,
                Mapping,
            ):
                continue

            value = item.get(
                "temperature_c",
                item.get(
                    "temperature",
                    item.get(
                        "temp"
                    ),
                ),
            )

            try:
                temperatures_c.append(
                    float(value)
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

        return tuple(
            temperatures_c
        )

    def telemetry_is_fresh(
        self,
        state: Mapping[str, Any],
    ) -> bool:
        """Return whether the supplied telemetry state is recent enough."""

        last_updated = state.get(
            "last_updated"
        )

        try:
            age = (
                self._clock()
                - float(last_updated)
            )
        except (
            TypeError,
            ValueError,
        ):
            return False

        return (
            age
            <= self._freshness_seconds
        )

    def snapshot(
        self,
    ) -> dict[str, Any]:
        """Return one normalized Host Agent safety snapshot."""

        state = self._state_provider()

        return {
            "fan_status": dict(
                self._fan_status_provider()
            ),
            "temperatures_c": (
                self.temperatures_from_state(
                    state
                )
            ),
            "telemetry_fresh": (
                self.telemetry_is_fresh(
                    state
                )
            ),
        }

    def __call__(
        self,
    ) -> dict[str, Any]:
        return self.snapshot()


__all__ = [
    "HostFanTelemetryProvider",
]
