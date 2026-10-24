"""
Construction helpers for the TruePanel Host Agent.

This module assembles the guarded fan command processor and Unix-socket server.
Application-owned LCD command handling lives outside the privileged Host
runtime.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from truepanel.cargo.copy_button import (
    LoadmasterCopyButtonGate,
)
from truepanel.hardware.fan_command import (
    FanCommandProcessor,
    FanCommandServer,
)
from truepanel.hardware.fintek_gpio import (
    FintekCopyButtonReader,
)

from .hooks import HostAgentSafetyServices
from .loadmaster_copy_button import (
    LoadmasterCopyButtonService,
)
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


def build_loadmaster_copy_button_service(
    *,
    config: Mapping[str, Any],
    reader_factory: Callable[[], Any] = FintekCopyButtonReader,
    on_confirmation: Callable[[Any], None] | None = None,
    event_recorder: Callable[[dict[str, object]], None] | None = None,
    preflight_provider: Callable[[], Any] | None = None,
) -> LoadmasterCopyButtonService | None:
    """Build the non-actuating physical Copy confirmation service."""

    mission = config.get("mission_control")
    if not isinstance(mission, Mapping):
        return None

    cargo = mission.get("cargo_bay")
    if not isinstance(cargo, Mapping):
        return None

    loadmaster = cargo.get("loadmaster")
    if not isinstance(loadmaster, Mapping):
        return None

    physical = loadmaster.get("physical_confirmation")
    if not isinstance(physical, Mapping):
        return None

    if physical.get("enabled") is not True:
        return None

    if str(physical.get("source") or "") != "fintek_gpio":
        raise ValueError(
            "unsupported Loadmaster physical confirmation source"
        )

    if int(physical.get("bank", -1)) != 7:
        raise ValueError(
            "Loadmaster Copy button bank must be verified GPIO bank 7"
        )

    if int(physical.get("bit", -1)) != 5:
        raise ValueError(
            "Loadmaster Copy button bit must be verified GPIO bit 5"
        )

    if physical.get("active_low") is not True:
        raise ValueError(
            "Loadmaster Copy button must be configured active-low"
        )

    debounce = float(physical.get("debounce_ms", 75)) / 1000.0
    rearm = float(physical.get("rearm_ms", 750)) / 1000.0
    window = float(
        physical.get("confirmation_window_seconds", 30)
    )

    reader = reader_factory()
    gate = LoadmasterCopyButtonGate(
        read_level=reader.read_level,
        debounce_seconds=debounce,
        rearm_seconds=rearm,
        confirmation_window_seconds=window,
        active_low=True,
    )

    return LoadmasterCopyButtonService(
        reader=reader,
        gate=gate,
        on_confirmation=on_confirmation,
        event_recorder=event_recorder,
        preflight_provider=preflight_provider,
    )

def build_host_agent_runtime(
    *,
    fan_runtime: Any,
    safety_services: HostAgentSafetyServices,
    ownership_guard: Any | None = None,
    fan_server_factory: Callable[[], Any | None] | None = None,
    loadmaster_copy_button_service: Any | None = None,
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

    if fan_server_factory is None:
        def fan_server_factory():
            return build_fan_command_server(
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

    return HostAgentRuntime(
        fan_runtime=fan_runtime,
        safety=safety,
        ownership_guard=ownership_guard,
        fan_status_reader=(
            safety_services.fan_status_reader
        ),
        fan_reconciliation=fan_reconciliation,
        thermal_lifecycle=thermal_lifecycle,
        fan_server_factory=fan_server_factory,
        loadmaster_copy_button_service=(
            loadmaster_copy_button_service
        ),
    )


def build_host_agent_runtime_from_bootstrap(
    *,
    bootstrap: Any,
    owner_name: str = "embedded-lcd",
    ownership_path: Any = DEFAULT_HOST_OWNERSHIP_PATH,
) -> HostAgentRuntime:
    """Assemble Host runtime behind one cross-process ownership lease."""

    config = getattr(bootstrap, "config", {}) or {}
    # The existing host agent retains exclusive GPIO75 ownership.
    # The v2 bridge is inert unless separately commissioned.
    v2 = config.get("loadmaster") or {}
    bridge_enabled = (
        isinstance(v2, Mapping)
        and v2.get("enabled") is True
        and v2.get("physical_bridge_enabled") is True
    )
    callback = None
    preflight_provider = None
    if bridge_enabled:
        from pathlib import Path

        from truepanel.loadmaster.evidence import qualified_preflight
        from truepanel.loadmaster.link import STATUS_PATH, read_status
        from truepanel.loadmaster.physical_bridge import ConfirmationBridge

        # Commissioning requires an independent verifier supplied by the host.
        # None is deliberately not evidence, even if all JSON files are valid.
        baseline_check = getattr(bootstrap, "loadmaster_baseline_verified", None)
        cargo = (config.get("mission_control") or {}).get("cargo_bay") or {}
        older = cargo.get("loadmaster") or {}
        registry = older.get("cartridge_registry_path")
        backlog = older.get("backlog_path")
        manifest = (cargo.get("backup") or {}).get("manifest_path")
        if (
            callable(baseline_check)
            and all(isinstance(p, str) and p.startswith("/") for p in (
                registry, backlog, manifest
            ))
        ):
            def preflight_provider():
                return qualified_preflight(
                    registry_path=Path(registry),
                    backlog_path=Path(backlog),
                    manifest_path=Path(manifest),
                    status=read_status(STATUS_PATH),
                    baseline_verified=baseline_check,
                )

            callback = ConfirmationBridge(enabled=True).accept

    loadmaster_copy_button_service = (
        build_loadmaster_copy_button_service(
            config=config,
            on_confirmation=callback,
            preflight_provider=preflight_provider,
        )
    )

    return build_host_agent_runtime(
        fan_runtime=bootstrap.fan_runtime,
        safety_services=bootstrap.safety_services(),
        ownership_guard=HostOwnershipGuard(
            owner_name,
            path=ownership_path,
        ),
        loadmaster_copy_button_service=(
            loadmaster_copy_button_service
        ),
    )


__all__ = [
    "build_fan_command_server",
    "build_loadmaster_copy_button_service",
    "build_host_agent_runtime",
    "build_host_agent_runtime_from_bootstrap",
]