"""
Host-owned safety telemetry.

The privileged Host Agent owns the narrow telemetry contract used by fan and
thermal safety logic. Storage temperatures are collected independently from
the broader application telemetry stack.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any


class HostFanTelemetryProvider:
    """
    Build the safety snapshot consumed by the Host Agent.

    A snapshot is fresh only when the Host Agent successfully obtains at least
    one valid temperature measurement during the current sampling cycle.
    """

    def __init__(
        self,
        *,
        temperature_provider: Callable[
            [],
            tuple[float, ...],
        ],
        fan_status_provider: Callable[
            [],
            Mapping[str, Any],
        ],
        clock: Callable[[], float] = time.time,
        freshness_seconds: float = 10.0,
    ) -> None:
        self._temperature_provider = (
            temperature_provider
        )
        self._fan_status_provider = (
            fan_status_provider
        )
        self._clock = clock
        self._freshness_seconds = float(
            freshness_seconds
        )
        self._last_successful_sample: (
            float | None
        ) = None

    def snapshot(
        self,
    ) -> dict[str, Any]:
        """Return one normalized Host Agent safety snapshot."""

        try:
            raw_temperatures = (
                self._temperature_provider()
            )
        except Exception:
            raw_temperatures = ()

        temperatures_c: list[float] = []

        for value in raw_temperatures:
            try:
                temperatures_c.append(
                    float(value)
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

        now = self._clock()

        if temperatures_c:
            self._last_successful_sample = now

        telemetry_fresh = False

        if (
            self._last_successful_sample
            is not None
        ):
            telemetry_fresh = (
                now
                - self._last_successful_sample
                <= self._freshness_seconds
            )

        return {
            "fan_status": dict(
                self._fan_status_provider()
            ),
            "temperatures_c": tuple(
                temperatures_c
            ),
            "telemetry_fresh": (
                telemetry_fresh
            ),
        }

    def __call__(
        self,
    ) -> dict[str, Any]:
        return self.snapshot()


__all__ = [
    "HostFanTelemetryProvider",
]
