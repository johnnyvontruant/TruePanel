"""
Construction helpers for the TruePanel Host Agent.

This module assembles the guarded fan command processor and Unix-socket server.
Application-owned LCD command handling lives outside the privileged Host
runtime.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from truepanel.hardware.fan_command import (
    FanCommandProcessor,
    FanCommandServer,
)

from .hooks import HostAgentSafetyServices
from .ownership import (
    DEFAULT_HOST_OWNERSHIP_PATH,
    HostOwnershipGuard,
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


def build_host_agent_runtime(
    *,
    fan_runtime: Any,
    safety_services: HostAgentSafetyServices,
    ownership_guard: Any | None = None,
) -> HostAgentRuntime:
    """Assemble the current privileged TruePanel Host Agent runtime."""

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

    thermal_lifecycle_factory = (
        safety_services
        .thermal_lifecycle_factory
    )
    thermal_lifecycle = (
        thermal_lifecycle_factory(safety)
        if thermal_lifecycle_factory is not None
        else None
    )

    return HostAgentRuntime(
        fan_runtime=fan_runtime,
        safety=safety,
        ownership_guard=ownership_guard,
        fan_status_reader=(
            safety_services.fan_status_reader
        ),
        fan_reconciliation=fan_reconciliation,
        thermal_lifecycle=thermal_lifecycle,
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
    )


def build_host_agent_runtime_from_bootstrap(
    *,
    bootstrap: Any,
    owner_name: str = "embedded-lcd",
    ownership_path: Any = DEFAULT_HOST_OWNERSHIP_PATH,
) -> HostAgentRuntime:
    """Assemble Host runtime behind one cross-process ownership lease."""

    return build_host_agent_runtime(
        fan_runtime=bootstrap.fan_runtime,
        safety_services=bootstrap.safety_services(),
        ownership_guard=HostOwnershipGuard(
            owner_name,
            path=ownership_path,
        ),
    )


__all__ = [
    "build_fan_command_server",
    "build_host_agent_runtime",
    "build_host_agent_runtime_from_bootstrap",
]
