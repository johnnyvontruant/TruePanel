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
from truepanel.hardware.fan_runtime import (
    build_fan_control_runtime,
)
from truepanel.hardware.thermal_commissioning import (
    thermal_commissioning_state,
)
from truepanel.history import (
    FanControlHistory,
    event_from_decision,
)
from truepanel.history.thermal_commissioning import (
    ThermalCommissioningHistory,
    commissioning_event,
)

from .thermal_authority import HostThermalAuthority

LOGGER = logging.getLogger(__name__)


@dataclass
class HostAgentBootstrap:
    """Own the privileged dependencies used by one Host Agent runtime."""

    config: dict[str, Any]
    fan_runtime: Any
    thermal_authority: HostThermalAuthority
    fan_control_history: FanControlHistory
    thermal_commissioning_history: ThermalCommissioningHistory

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
    thermal_authority_factory=HostThermalAuthority,
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

    thermal = _thermal_policy_config(
        config
    )

    thermal_authority = thermal_authority_factory(
        service=fan_runtime.service,
        policy_mode=(
            _thermal_policy_mode(
                config
            )
        ),
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

    return HostAgentBootstrap(
        config=config,
        fan_runtime=fan_runtime,
        thermal_authority=thermal_authority,
        fan_control_history=fan_control_history,
        thermal_commissioning_history=(
            thermal_commissioning_history
        ),
    )


__all__ = [
    "HostAgentBootstrap",
    "build_host_agent_bootstrap",
]
