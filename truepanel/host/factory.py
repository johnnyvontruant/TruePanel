"""
Construction helpers for the TruePanel Host Agent.

This module assembles existing guarded command processors and Unix-socket
servers. Application-specific telemetry, status, history, thermal policy, and
LCD behavior remain injected callbacks.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from truepanel.hardware.fan_command import (
    FanCommandProcessor,
    FanCommandServer,
)
from truepanel.hardware.lcd_command import (
    LCDCommandProcessor,
    LCDCommandServer,
)

from .hooks import (
    HostAgentApplicationHooks,
    HostAgentSafetyServices,
)
from .runtime import HostAgentRuntime
from .safety import HostAgentSafetyCoordinator


def build_fan_command_server(
    *,
    fan_runtime: Any,
    telemetry_provider: Callable[
        [],
        Mapping[str, Any],
    ],
    status_publisher: Callable[[], None] | None = None,
    event_recorder: Callable[
        [
            Any,
            Mapping[str, Any],
        ],
        None,
    ] | None = None,
    thermal_control_handler: Callable[
        [str],
        Mapping[str, Any],
    ] | None = None,
) -> FanCommandServer | None:
    """
    Build the guarded fan command server.

    A disabled fan runtime exposes no fan-control command socket.
    """

    if not fan_runtime.enabled:
        return None

    processor = FanCommandProcessor(
        fan_runtime,
        telemetry_provider=telemetry_provider,
        status_publisher=status_publisher,
        event_recorder=event_recorder,
        thermal_control_handler=(
            thermal_control_handler
        ),
    )

    return FanCommandServer(
        processor
    )


def build_lcd_command_server(
    *,
    submit_button: Callable[
        [int, str],
        bool,
    ] | None,
) -> LCDCommandServer | None:
    """
    Build the guarded LCD command server.

    Hosts without an LCD submission callback expose no LCD command socket.
    """

    if submit_button is None:
        return None

    processor = LCDCommandProcessor(
        submit_button
    )

    return LCDCommandServer(
        processor
    )


def build_host_agent_runtime(
    *,
    fan_runtime: Any,
    safety_services: HostAgentSafetyServices,
    application_hooks: HostAgentApplicationHooks,
) -> HostAgentRuntime:
    """
    Assemble the current TruePanel Host Agent runtime.

    Safety behavior is grouped behind HostAgentSafetyCoordinator while
    application behavior remains an explicit non-privileged hook surface.
    """

    safety = HostAgentSafetyCoordinator(
        fan_runtime=fan_runtime,
        telemetry_provider=(
            safety_services
            .fan_telemetry_provider
        ),
        status_publisher=(
            safety_services
            .fan_status_publisher
        ),
        event_recorder=(
            safety_services
            .fan_event_recorder
        ),
    )

    thermal_control_handler_factory = (
        safety_services
        .thermal_control_handler_factory
    )

    if thermal_control_handler_factory is not None:
        safety.bind_thermal_control_handler(
            thermal_control_handler_factory(
                safety.restore_automatic
            )
        )

    fan_reconciliation_factory = (
        safety_services
        .fan_reconciliation_factory
    )
    fan_reconciliation = (
        fan_reconciliation_factory(safety)
        if fan_reconciliation_factory is not None
        else None
    )

    runtime = HostAgentRuntime(
        fan_runtime=fan_runtime,
        safety=safety,
        fan_reconciliation=fan_reconciliation,
        fan_server_factory=lambda: (
            build_fan_command_server(
                fan_runtime=fan_runtime,
                telemetry_provider=(
                    safety.telemetry
                ),
                status_publisher=(
                    safety.publish_status
                ),
                event_recorder=lambda decision, telemetry: (
                    safety.record_event(
                        decision,
                        telemetry,
                        source="manual",
                    )
                ),
                thermal_control_handler=(
                    safety.handle_thermal_control
                ),
            )
        ),
        lcd_server_factory=lambda: (
            build_lcd_command_server(
                submit_button=(
                    application_hooks
                    .lcd_button_handler
                ),
            )
        ),
    )

    return runtime


__all__ = [
    "build_fan_command_server",
    "build_host_agent_runtime",
    "build_lcd_command_server",
]
