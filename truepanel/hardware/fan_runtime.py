"""
Root-owned fan-control runtime integration.

This module conditionally constructs the interlock, executor, and service only
when fan control is explicitly enabled. Disabled or unavailable configurations
remain safely disconnected and publish Automatic status.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from truepanel.hardware.discovery import (
    find_fintek_hwmon,
)
from truepanel.hardware.fan_control import (
    FanControlInterlock,
)
from truepanel.hardware.fan_executor import (
    FanHardwareExecutor,
)
from truepanel.hardware.fan_service import (
    FanControlService,
)

LOGGER = logging.getLogger(__name__)


@dataclass
class FanControlRuntime:
    enabled: bool
    service: FanControlService | None = None
    unavailable_reason: str | None = None

    @property
    def connected(self) -> bool:
        return (
            self.enabled
            and self.service is not None
        )

    def status_payload(self) -> dict[str, Any]:
        if not self.enabled:
            return {
                "enabled": False,
                "connected": False,
                "active_profile": "automatic",
                "requested_profile": "automatic",
                "remaining_seconds": None,
                "last_reason": (
                    "Fan control is disabled."
                ),
                "control_authority": "automatic",
                "safety_hold": False,
                "recovery_pending": False,
                "recovery_healthy_cycles": 0,
                "recovery_required_cycles": 3,
            }

        if self.service is None:
            return {
                "enabled": True,
                "connected": False,
                "active_profile": "automatic",
                "requested_profile": "automatic",
                "remaining_seconds": None,
                "last_reason": (
                    self.unavailable_reason
                    or (
                        "Fan control could not be "
                        "connected safely."
                    )
                ),
                "control_authority": "automatic",
                "safety_hold": False,
                "recovery_pending": False,
                "recovery_healthy_cycles": 0,
                "recovery_required_cycles": 3,
            }

        status = self.service.status()

        return {
            "enabled": True,
            "connected": True,
            "active_profile": (
                status.active_profile.value
            ),
            "requested_profile": (
                status.requested_profile.value
            ),
            "remaining_seconds": (
                status.remaining_seconds
            ),
            "last_reason": (
                status.last_reason
            ),
            "control_authority": (
                status.control_authority
            ),
            "safety_hold": (
                status.safety_hold
            ),
            "recovery_pending": (
                status.recovery_pending
            ),
            "recovery_healthy_cycles": (
                status.recovery_healthy_cycles
            ),
            "recovery_required_cycles": (
                status.recovery_required_cycles
            ),
        }

    def shutdown(self) -> None:
        if self.service is None:
            return

        try:
            self.service.shutdown()
        finally:
            self.service = None


def _normalize_channels(
    raw_channels: Any,
) -> tuple[int, ...]:
    if not isinstance(
        raw_channels,
        (
            list,
            tuple,
        ),
    ):
        raw_channels = (
            1,
            2,
        )

    channels = []

    for value in raw_channels:
        try:
            channel = int(
                value
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        if (
            channel in (
                1,
                2,
            )
            and channel not in channels
        ):
            channels.append(
                channel
            )

    if not channels:
        channels = [
            1,
            2,
        ]

    return tuple(
        channels
    )


def build_fan_control_runtime(
    config: Mapping[str, Any],
    *,
    controller_factory: Callable[
        [],
        str | Path | None,
    ] = find_fintek_hwmon,
    interlock_factory: Callable[
        ...,
        FanControlInterlock,
    ] = FanControlInterlock,
    executor_factory: Callable[
        ...,
        FanHardwareExecutor,
    ] = FanHardwareExecutor,
    service_factory: Callable[
        ...,
        FanControlService,
    ] = FanControlService,
) -> FanControlRuntime:
    hardware = config.get(
        "hardware",
        {},
    )

    if not isinstance(
        hardware,
        Mapping,
    ):
        hardware = {}

    settings = hardware.get(
        "fan_control",
        {},
    )

    if not isinstance(
        settings,
        Mapping,
    ):
        settings = {}

    enabled = bool(
        settings.get(
            "enabled",
            False,
        )
    )

    if not enabled:
        return FanControlRuntime(
            enabled=False,
        )

    channels = _normalize_channels(
        settings.get(
            "controlled_channels",
            (
                1,
                2,
            ),
        )
    )

    try:
        timeout = max(
            0.0,
            float(
                settings.get(
                    "command_timeout",
                    300,
                )
            ),
        )
    except (
        TypeError,
        ValueError,
    ):
        timeout = 300.0

    try:
        afterburners_timeout = max(
            0.0,
            float(
                settings.get(
                    "afterburners_timeout",
                    120,
                )
            ),
        )
    except (
        TypeError,
        ValueError,
    ):
        afterburners_timeout = 120.0

    try:
        safety_recovery_cycles = max(
            1,
            int(
                settings.get(
                    "safety_recovery_cycles",
                    3,
                )
            ),
        )
    except (
        TypeError,
        ValueError,
    ):
        safety_recovery_cycles = 3

    try:
        base = controller_factory()

        if base is None:
            return FanControlRuntime(
                enabled=True,
                unavailable_reason=(
                    "Fintek fan controller is unavailable."
                ),
            )

        interlock = interlock_factory(
            controlled_channels=channels,
        )

        executor = executor_factory(
            base,
            controlled_channels=channels,
        )

        try:
            service = service_factory(
                    interlock,
                    executor,
                    command_timeout=timeout,
                    afterburners_timeout=(
                        afterburners_timeout
                    ),
                    safety_recovery_cycles=(
                        safety_recovery_cycles
                    ),
                )
        except Exception:
            executor.close()
            raise

        LOGGER.info(
            "Fan control runtime connected on channels %s",
            channels,
        )

        return FanControlRuntime(
            enabled=True,
            service=service,
        )
    except Exception as error:
        LOGGER.exception(
            "Fan control runtime could not be connected"
        )

        return FanControlRuntime(
            enabled=True,
            unavailable_reason=(
                "Fan control connection failed: "
                f"{type(error).__name__}: {error}"
            ),
        )


__all__ = [
    "FanControlRuntime",
    "build_fan_control_runtime",
]
