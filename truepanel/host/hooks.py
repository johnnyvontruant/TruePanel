"""
Explicit privileged service contracts for the TruePanel Host Agent.

These contracts define Host-owned safety dependencies. They do not grant
hardware authority.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

FanTelemetryProvider = Callable[
    [],
    Mapping[str, Any],
]

FanStatusPublisher = Callable[..., Any]

FanStatusReader = Callable[..., Mapping[str, Any] | None]

FanEventRecorder = Callable[
    [
        Any,
        Mapping[str, Any],
        str,
    ],
    None,
]

ThermalControlHandler = Callable[
    [str],
    Mapping[str, Any],
]

ThermalAutomaticRestorer = Callable[..., Any]

ThermalControlHandlerFactory = Callable[
    [ThermalAutomaticRestorer],
    ThermalControlHandler,
]

FanReconciliationFactory = Callable[[Any], Any]


@dataclass(frozen=True)
class HostAgentSafetyServices:
    """Safety-related services consumed by the privileged Host Agent."""

    fan_telemetry_provider: FanTelemetryProvider
    fan_status_publisher: FanStatusPublisher | None = None
    fan_status_reader: FanStatusReader | None = None
    fan_event_recorder: FanEventRecorder | None = None
    thermal_control_handler_factory: (
        ThermalControlHandlerFactory | None
    ) = None
    fan_reconciliation_factory: (
        FanReconciliationFactory | None
    ) = None
    thermal_lifecycle_factory: Callable[[Any], Any] | None = None


__all__ = [
    "FanEventRecorder",
    "FanStatusPublisher",
    "FanStatusReader",
    "FanTelemetryProvider",
    "HostAgentSafetyServices",
    "ThermalAutomaticRestorer",
    "ThermalControlHandler",
    "ThermalControlHandlerFactory",
]
