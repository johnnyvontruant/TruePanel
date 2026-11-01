"""
Safety-gated fan-health monitoring for Mission Control.

Only channels explicitly configured with ``monitored: true`` are evaluated.
The watcher is read-only and never changes PWM or controller state.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from truepanel.hardware.fans import get_status as get_fan_status
from truepanel.mission_control.constants import Category, Priority
from truepanel.mission_control.event import MissionEvent


DEFAULT_FAN_HEALTH_CONFIG = {
    "enabled": True,
    "interval": 10,
    "minimum_rpm": 300,
    "consecutive_failures": 3,
    "emit_initial_conditions": False,
}


def get_fan_health_config(
    config: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return fan-health settings merged with production defaults."""

    settings = dict(DEFAULT_FAN_HEALTH_CONFIG)

    if not isinstance(config, Mapping):
        return settings

    mission_control = config.get(
        "mission_control",
        {},
    )

    if isinstance(
        mission_control,
        Mapping,
    ):
        overrides = mission_control.get(
            "fan_health",
            {},
        )

        if isinstance(
            overrides,
            Mapping,
        ):
            settings.update(
                overrides
            )

    return settings


def get_fan_channel_config(
    config: Mapping[str, Any] | None,
) -> dict[int, dict[str, Any]]:
    """Normalize configured fan channel metadata to integer channel keys."""

    if not isinstance(config, Mapping):
        return {}

    hardware = config.get(
        "hardware",
        {},
    )

    if not isinstance(
        hardware,
        Mapping,
    ):
        return {}

    fans = hardware.get(
        "fans",
        {},
    )

    if not isinstance(
        fans,
        Mapping,
    ):
        return {}

    channels = fans.get(
        "channels",
        {},
    )

    if not isinstance(
        channels,
        Mapping,
    ):
        return {}

    normalized = {}

    for key, value in channels.items():
        try:
            number = int(key)
        except (
            TypeError,
            ValueError,
        ):
            continue

        if number <= 0:
            continue

        if isinstance(
            value,
            Mapping,
        ):
            normalized[number] = dict(
                value
            )

    return normalized


class FanHealthWatcher:
    """
    Debounce low-RPM conditions and emit transition events.

    A monitored channel must remain below ``minimum_rpm`` for
    ``consecutive_failures`` observations before a warning is emitted.
    Recovery is emitted once when the channel returns to a healthy RPM.
    """

    def __init__(
        self,
        *,
        status_provider: Callable[
            [],
            Mapping[str, Any],
        ] = get_fan_status,
        channels: Mapping[
            int,
            Mapping[str, Any],
        ] | None = None,
        interval: float = 10,
        minimum_rpm: int = 300,
        consecutive_failures: int = 3,
        emit_initial_conditions: bool = False,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.status_provider = (
            status_provider
        )
        self.channels = {
            int(number): dict(settings)
            for number, settings
            in (
                channels
                or {}
            ).items()
        }

        self.interval = max(
            0.0,
            float(interval),
        )
        self.minimum_rpm = max(
            0,
            int(minimum_rpm),
        )
        self.consecutive_failures = max(
            1,
            int(consecutive_failures),
        )
        self.emit_initial_conditions = bool(
            emit_initial_conditions
        )
        self.clock = clock

        self.last_check = None
        self.failure_counts = {}
        self.failed_channels = set()
        self.initial_unhealthy_channels = set()
        self.initialized = False

    def _configured_channel(
        self,
        number: int,
    ) -> dict[str, Any]:
        return self.channels.get(
            number,
            {},
        )

    def _label(
        self,
        number: int,
    ) -> str:
        configured = (
            self._configured_channel(
                number
            )
        )

        return str(
            configured.get(
                "label",
                f"Fan {number}",
            )
        )

    def _monitored(
        self,
        number: int,
    ) -> bool:
        configured = (
            self._configured_channel(
                number
            )
        )

        return bool(
            configured.get(
                "monitored",
                False,
            )
        )

    def _warning_event(
        self,
        number: int,
        rpm: int,
    ) -> MissionEvent:
        label = self._label(
            number
        )

        return MissionEvent(
            priority=Priority.WARNING,
            title="FAN ALERT",
            message=f"{label} {rpm} RPM",
            category=Category.THERMAL,
            timeout=15,
            event_id=(
                f"thermal.fan{number}."
                "low_rpm"
            ),
            source="fan_health_watcher",
            metadata={
                "change_type": (
                    "fan_low_rpm"
                ),
                "channel": number,
                "label": label,
                "rpm": rpm,
                "minimum_rpm": (
                    self.minimum_rpm
                ),
                "monitored": True,
            },
        )

    def _recovery_event(
        self,
        number: int,
        rpm: int,
    ) -> MissionEvent:
        label = self._label(
            number
        )

        return MissionEvent(
            priority=Priority.HEALTHY,
            title="FAN RECOVERED",
            message=f"{label} {rpm} RPM",
            category=Category.THERMAL,
            timeout=7,
            event_id=(
                f"thermal.fan{number}."
                "recovered"
            ),
            source="fan_health_watcher",
            metadata={
                "change_type": (
                    "fan_recovered"
                ),
                "channel": number,
                "label": label,
                "rpm": rpm,
                "minimum_rpm": (
                    self.minimum_rpm
                ),
                "monitored": True,
            },
        )

    def __call__(
        self,
        state,
    ):
        now = self.clock()

        if (
            self.last_check
            is not None
            and now - self.last_check
            < self.interval
        ):
            return None

        self.last_check = now

        try:
            status = dict(
                self.status_provider()
                or {}
            )
        except Exception:
            return None

        channels = status.get(
            "fan_channels",
            [],
        )

        if not isinstance(
            channels,
            list,
        ):
            return None

        first_observation = (
            not self.initialized
        )
        self.initialized = True

        for channel in channels:
            if not isinstance(
                channel,
                Mapping,
            ):
                continue

            try:
                number = int(
                    channel.get(
                        "number",
                        0,
                    )
                )
                rpm = max(
                    0,
                    int(
                        channel.get(
                            "rpm",
                            0,
                        )
                        or 0
                    ),
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            if not self._monitored(
                number
            ):
                self.failure_counts.pop(
                    number,
                    None,
                )
                self.failed_channels.discard(
                    number
                )
                continue

            unhealthy = (
                rpm
                < self.minimum_rpm
            )

            if unhealthy:
                if first_observation:
                    self.initial_unhealthy_channels.add(
                        number
                    )

                count = (
                    self.failure_counts.get(
                        number,
                        0,
                    )
                    + 1
                )
                self.failure_counts[
                    number
                ] = count

                if (
                    number
                    in self.failed_channels
                ):
                    continue

                if (
                    count
                    < self.consecutive_failures
                ):
                    continue

                self.failed_channels.add(
                    number
                )

                if (
                    number
                    in self.initial_unhealthy_channels
                    and not self.emit_initial_conditions
                ):
                    continue

                return self._warning_event(
                    number,
                    rpm,
                )

            self.failure_counts[
                number
            ] = 0

            if (
                number
                in self.failed_channels
            ):
                self.failed_channels.remove(
                    number
                )
                self.initial_unhealthy_channels.discard(
                    number
                )

                return self._recovery_event(
                    number,
                    rpm,
                )

            self.initial_unhealthy_channels.discard(
                number
            )

        return None


def build_fan_health_watcher(
    config: Mapping[str, Any] | None,
    *,
    status_provider: Callable[
        [],
        Mapping[str, Any],
    ] = get_fan_status,
    clock: Callable[[], float] | None = None,
) -> FanHealthWatcher | None:
    """Construct the configured production fan-health watcher."""

    settings = get_fan_health_config(
        config
    )

    if not bool(
        settings.get(
            "enabled",
            True,
        )
    ):
        return None

    kwargs = {
        "status_provider": (
            status_provider
        ),
        "channels": (
            get_fan_channel_config(
                config
            )
        ),
        "interval": settings.get(
            "interval",
            10,
        ),
        "minimum_rpm": settings.get(
            "minimum_rpm",
            300,
        ),
        "consecutive_failures": (
            settings.get(
                "consecutive_failures",
                3,
            )
        ),
        "emit_initial_conditions": (
            settings.get(
                "emit_initial_conditions",
                False,
            )
        ),
    }

    if clock is not None:
        kwargs["clock"] = clock

    return FanHealthWatcher(
        **kwargs
    )


__all__ = [
    "DEFAULT_FAN_HEALTH_CONFIG",
    "FanHealthWatcher",
    "build_fan_health_watcher",
    "get_fan_channel_config",
    "get_fan_health_config",
]
