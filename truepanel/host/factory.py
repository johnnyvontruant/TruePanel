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

from .runtime import HostAgentRuntime


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
    fan_telemetry_provider: Callable[
        [],
        Mapping[str, Any],
    ],
    fan_status_publisher: Callable[
        [],
        None,
    ] | None = None,
    fan_event_recorder: Callable[
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
    lcd_button_handler: Callable[
        [int, str],
        bool,
    ] | None = None,
) -> HostAgentRuntime:
    """
    Assemble the current TruePanel Host Agent runtime.

    This function owns command-server construction only. It does not start the
    runtime and grants no additional hardware authority.
    """

    return HostAgentRuntime(
        fan_runtime=fan_runtime,
        fan_server_factory=lambda: (
            build_fan_command_server(
                fan_runtime=fan_runtime,
                telemetry_provider=(
                    fan_telemetry_provider
                ),
                status_publisher=(
                    fan_status_publisher
                ),
                event_recorder=(
                    fan_event_recorder
                ),
                thermal_control_handler=(
                    thermal_control_handler
                ),
            )
        ),
        lcd_server_factory=lambda: (
            build_lcd_command_server(
                submit_button=(
                    lcd_button_handler
                ),
            )
        ),
    )


__all__ = [
    "build_fan_command_server",
    "build_host_agent_runtime",
    "build_lcd_command_server",
]
