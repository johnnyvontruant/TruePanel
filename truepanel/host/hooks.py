"""
Explicit process-boundary contracts for the TruePanel Host Agent.

Safety services describe behavior that belongs on the privileged Host Agent
side of the architecture.

Application hooks describe behavior that belongs outside the privileged Host
Agent and may eventually cross an IPC boundary.

These contracts define ownership. They do not grant hardware authority.
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

LCDButtonHandler = Callable[
    [int, str],
    bool,
]


@dataclass(frozen=True)
class HostAgentSafetyServices:
    """
    Safety-related services consumed by the privileged Host Agent.

    Some services are still supplied by the legacy LCD runtime during the
    migration. Their presence here defines their intended ownership boundary.
    """

    fan_telemetry_provider: FanTelemetryProvider
    fan_status_publisher: FanStatusPublisher | None = None
    fan_event_recorder: FanEventRecorder | None = None
    thermal_control_handler_factory: (
        ThermalControlHandlerFactory | None
    ) = None
    fan_reconciliation_factory: (
        FanReconciliationFactory | None
    ) = None


@dataclass(frozen=True)
class HostAgentApplicationHooks:
    """
    Non-privileged application behavior exposed to the Host Agent.

    These hooks must not be treated as hardware authorization.
    """

    lcd_button_handler: LCDButtonHandler | None = None


__all__ = [
    "FanEventRecorder",
    "FanStatusPublisher",
    "FanTelemetryProvider",
    "HostAgentApplicationHooks",
    "HostAgentSafetyServices",
    "LCDButtonHandler",
    "ThermalAutomaticRestorer",
    "ThermalControlHandler",
    "ThermalControlHandlerFactory",
]
