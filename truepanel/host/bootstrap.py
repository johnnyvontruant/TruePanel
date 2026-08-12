"""
Production dependency ownership for the TruePanel Host Agent.

This module extracts privileged Host Agent construction from the legacy LCD
runtime without changing the active process boundary. Standalone activation
remains locked until the migration is explicitly completed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from truepanel.hardware.bounded_automatic import (
    AUTOMATIC_LEASE_SECONDS,
    thermal_safety_fingerprint,
)
from truepanel.hardware.drive_temperatures import (
    DriveTemperatureProvider,
)
from truepanel.hardware.fans import (
    get_status as get_fan_status,
)
from truepanel.hardware.fan_status_bridge import (
    FanControlStatusBridge,
)
from truepanel.hardware.fan_runtime import (
    build_fan_control_runtime,
)
from truepanel.hardware.thermal_commissioning import (
    thermal_commissioning_state,
)
from truepanel.hardware.thermal_fan_policy import ThermalFanPolicy
from truepanel.history import (
    FanControlHistory,
    ThermalObserverHistory,
    event_from_decision,
)
from truepanel.history.thermal_commissioning import (
    ThermalCommissioningHistory,
    commissioning_event,
)

from .hooks import (
    HostAgentSafetyServices,
    ThermalAutomaticRestorer,
    ThermalControlHandler,
)
from .reconciliation import (
    HostFanReconciliationCoordinator,
)
from .status import publish_host_fan_status
from .telemetry import HostFanTelemetryProvider
from .thermal_authority import HostThermalAuthority
from .thermal_observer import HostThermalObserver

LOGGER = logging.getLogger(__name__)


@dataclass
class HostAgentBootstrap:
    """Own the privileged dependencies used by one Host Agent runtime."""

    config: dict[str, Any]
    fan_runtime: Any
    thermal_authority: HostThermalAuthority
    thermal_observer: HostThermalObserver
    fan_control_history: FanControlHistory
    thermal_commissioning_history: ThermalCommissioningHistory
    telemetry: HostFanTelemetryProvider
    status_bridge: FanControlStatusBridge

    def publish_fan_status(
        self,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Publish one authoritative Host fan/thermal status snapshot."""

        return publish_host_fan_status(
            fan_runtime=self.fan_runtime,
            thermal_authority=self.thermal_authority,
            status_bridge=self.status_bridge,
            reason=reason,
        )

    def build_thermal_control_handler(
        self,
        restore_automatic: ThermalAutomaticRestorer,
    ) -> ThermalControlHandler:
        """Bind thermal actions to Host safety restoration after construction."""

        def handle(
            action: str,
        ):
            return self.thermal_authority.handle_action(
                action,
                telemetry_provider=(
                    self.telemetry.snapshot
                ),
                runtime_status_provider=(
                    self.fan_runtime.status_payload
                ),
                restore_automatic=restore_automatic,
                record_commissioning_event=(
                    self.record_commissioning_event
                ),
            )

        return handle

    def build_fan_reconciliation(
        self,
        safety: Any,
    ) -> HostFanReconciliationCoordinator:
        """Build Host-owned fan/thermal reconciliation after safety exists."""

        return HostFanReconciliationCoordinator(
            fan_runtime=self.fan_runtime,
            safety=safety,
            thermal_observer=self.thermal_observer,
            thermal_authority=self.thermal_authority,
            fan_event_source=self.fan_event_source,
            record_fan_event=self.record_fan_event,
            record_commissioning_event=(
                self.record_commissioning_event
            ),
        )

    def safety_services(
        self,
    ) -> HostAgentSafetyServices:
        """Build the privileged service bundle consumed by Host runtime."""

        return HostAgentSafetyServices(
            fan_telemetry_provider=(
                self.telemetry.snapshot
            ),
            fan_status_publisher=(
                self.publish_fan_status
            ),
            fan_event_recorder=(
                lambda decision, telemetry, source: (
                    self.record_fan_event(
                        decision,
                        dict(telemetry),
                        source=source,
                    )
                )
            ),
            thermal_control_handler_factory=(
                self.build_thermal_control_handler
            ),
            fan_reconciliation_factory=(
                self.build_fan_reconciliation
            ),
        )

    def record_fan_event(
        self,
        decision: Any,
        telemetry: dict[str, Any],
        *,
        source: str,
    ) -> None:
        """Record one authoritative Host fan-control decision."""

        try:
            self.fan_control_history.append(
                event_from_decision(
                    decision,
                    source=source,
                    telemetry=telemetry,
                )
            )
        except Exception:
            LOGGER.exception(
                "Could not append fan-control history"
            )

    @staticmethod
    def fan_event_source(
        decision: Any,
    ) -> str:
        """Classify a Host fan-safety decision for history."""

        reason_lower = decision.reason.lower()

        if (
            decision.force_automatic
            and "safety recovery confirmed"
            in reason_lower
        ):
            return "recovery"

        if (
            decision.force_automatic
            and "expired" in reason_lower
        ):
            return "timeout"

        return "safety"

    def record_commissioning_event(
        self,
        lifecycle_action: str,
        reason: str,
        *,
        lease_remaining: float | None = None,
    ) -> None:
        """Record one normalized Host thermal-authority lifecycle event."""

        runtime_status = (
            self.fan_runtime.status_payload()
        )

        if lease_remaining is None:
            lease_remaining = (
                self.thermal_authority
                .supervised_session_remaining()
            )

        state = thermal_commissioning_state(
            policy_mode=(
                self.thermal_authority.policy_mode
            ),
            operator_armed=(
                self.thermal_authority.operator_armed
            ),
            dry_run=(
                self.thermal_authority
                .coordinator
                .dry_run
            ),
            supervised_session_active=(
                self.thermal_authority
                .supervised_session_active()
            ),
        )

        try:
            self.thermal_commissioning_history.append(
                commissioning_event(
                    lifecycle_action=lifecycle_action,
                    reason=reason,
                    commissioning_state=state,
                    active_profile=runtime_status.get(
                        "active_profile",
                        "automatic",
                    ),
                    control_authority=runtime_status.get(
                        "control_authority",
                        "automatic",
                    ),
                    lease_remaining=lease_remaining,
                )
            )
        except Exception:
            LOGGER.exception(
                "Could not append thermal commissioning history"
            )


def _thermal_policy_config(
    config: dict[str, Any],
) -> dict[str, Any]:
    hardware = config.get(
        "hardware",
        {},
    )

    if not isinstance(
        hardware,
        dict,
    ):
        hardware = {}

    thermal = hardware.get(
        "thermal_policy",
        {},
    )

    if not isinstance(
        thermal,
        dict,
    ):
        thermal = {}

    return thermal


def _thermal_policy_mode(
    config: dict[str, Any],
) -> str:
    thermal = _thermal_policy_config(
        config
    )

    mode = str(
        thermal.get(
            "mode",
            "observe_only",
        )
    ).strip().lower()

    if mode not in {
        "disabled",
        "observe_only",
        "automatic_control",
    }:
        return "observe_only"

    return mode


def build_host_agent_bootstrap(
    config: dict[str, Any],
    *,
    fan_runtime_factory=build_fan_control_runtime,
    fan_history_factory=FanControlHistory,
    commissioning_history_factory=(
        ThermalCommissioningHistory
    ),
    thermal_observer_history_factory=ThermalObserverHistory,
    drive_temperature_provider_factory=DriveTemperatureProvider,
    fan_status_provider=get_fan_status,
    telemetry_factory=HostFanTelemetryProvider,
    status_bridge_factory=FanControlStatusBridge,
    thermal_policy_factory=ThermalFanPolicy,
    thermal_authority_factory=HostThermalAuthority,
    thermal_observer_factory=HostThermalObserver,
) -> HostAgentBootstrap:
    """
    Construct Host-owned runtime dependencies.

    Construction never grants hardware authority. Thermal authority remains
    ephemeral and always starts disarmed in dry-run mode.
    """

    fan_runtime = fan_runtime_factory(
        config
    )

    history = config.get(
        "history",
        {},
    )

    if not isinstance(
        history,
        dict,
    ):
        history = {}

    history_enabled = bool(
        history.get(
            "enabled",
            True,
        )
    )

    fan_control_history = fan_history_factory(
        history.get(
            "fan_control_path",
            (
                "/var/lib/truepanel/history/"
                "fan-control.jsonl"
            ),
        ),
        enabled=history_enabled,
    )

    thermal_commissioning_history = (
        commissioning_history_factory(
            history.get(
                "thermal_commissioning_path",
                (
                    "/var/lib/truepanel/history/"
                    "thermal-commissioning.jsonl"
                ),
            ),
            enabled=history_enabled,
        )
    )

    thermal_observer_history = (
        thermal_observer_history_factory(
            history.get(
                "thermal_observer_path",
                (
                    "/var/lib/truepanel/history/"
                    "thermal-observer.jsonl"
                ),
            ),
            enabled=history_enabled,
        )
    )

    thermal = _thermal_policy_config(
        config
    )
    policy_mode = _thermal_policy_mode(
        config
    )

    thermal_authority = thermal_authority_factory(
        service=fan_runtime.service,
        policy_mode=policy_mode,
        command_cooldown_seconds=float(
            thermal.get(
                "command_cooldown_seconds",
                30,
            )
        ),
        current_fingerprint=(
            thermal_safety_fingerprint(
                config
            )
        ),
        commissioned_fingerprint=str(
            thermal.get(
                "commissioned_fingerprint",
                "",
            )
            or ""
        ).strip().lower(),
        automatic_lease_seconds=(
            AUTOMATIC_LEASE_SECONDS
        ),
        supervised_session_seconds=120.0,
    )

    thermal_policy = thermal_policy_factory(
        balanced_temperature_c=float(
            thermal.get(
                "balanced_temperature_c",
                42,
            )
        ),
        cooling_boost_temperature_c=float(
            thermal.get(
                "cooling_boost_temperature_c",
                50,
            )
        ),
        afterburners_temperature_c=float(
            thermal.get(
                "afterburners_temperature_c",
                60,
            )
        ),
        hysteresis_c=float(
            thermal.get(
                "hysteresis_c",
                3,
            )
        ),
        minimum_dwell_seconds=float(
            thermal.get(
                "minimum_dwell_seconds",
                30,
            )
        ),
    )

    thermal_observer = thermal_observer_factory(
        policy=thermal_policy,
        policy_mode=policy_mode,
        thermal_authority=thermal_authority,
        history=thermal_observer_history,
        runtime_status_provider=(
            lambda: fan_runtime.status_payload()
        ),
    )

    drive_temperature_provider = (
        drive_temperature_provider_factory()
    )

    telemetry = telemetry_factory(
        temperature_provider=(
            drive_temperature_provider
        ),
        fan_status_provider=fan_status_provider,
    )

    status_bridge = status_bridge_factory()

    return HostAgentBootstrap(
        config=config,
        fan_runtime=fan_runtime,
        thermal_authority=thermal_authority,
        thermal_observer=thermal_observer,
        telemetry=telemetry,
        status_bridge=status_bridge,
        fan_control_history=fan_control_history,
        thermal_commissioning_history=(
            thermal_commissioning_history
        ),
    )


__all__ = [
    "HostAgentBootstrap",
    "build_host_agent_bootstrap",
]
