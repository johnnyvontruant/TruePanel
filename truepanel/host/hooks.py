"""
Application callback contract for the TruePanel Host Agent.

These hooks describe application-owned behavior that the Host Agent may invoke.
They do not grant hardware authority and contain no lifecycle logic.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

FanTelemetryProvider = Callable[
    [],
    Mapping[str, Any],
]

FanStatusPublisher = Callable[
    [],
    None,
]

FanEventRecorder = Callable[
    [
        Any,
        Mapping[str, Any],
    ],
    None,
]

ThermalControlHandler = Callable[
    [str],
    Mapping[str, Any],
]

LCDButtonHandler = Callable[
    [int, str],
    bool,
]


@dataclass(frozen=True)
class HostAgentApplicationHooks:
    """
    Application-owned callbacks exposed to the Host Agent.

    The Host Agent may invoke these callbacks but does not own their policy,
    state, or authorization rules.
    """

    fan_telemetry_provider: FanTelemetryProvider
    fan_status_publisher: FanStatusPublisher | None = None
    fan_event_recorder: FanEventRecorder | None = None
    thermal_control_handler: ThermalControlHandler | None = None
    lcd_button_handler: LCDButtonHandler | None = None


__all__ = [
    "FanEventRecorder",
    "FanStatusPublisher",
    "FanTelemetryProvider",
    "HostAgentApplicationHooks",
    "LCDButtonHandler",
    "ThermalControlHandler",
]
