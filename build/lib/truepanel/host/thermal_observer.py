"""
Host-owned thermal observation and recommendation history.

This module evaluates thermal guidance and records recommendation transitions.
It is deliberately observation-only: it does not request fan profiles, invoke
command sockets, or write hardware state.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from truepanel.hardware.thermal_fan_policy import ThermalFanPolicy
from truepanel.history import ThermalObserverHistory, event_from_recommendation

LOGGER = logging.getLogger(__name__)


class HostThermalObserver:
    """Own thermal policy evaluation and observer-history publication."""

    def __init__(
        self,
        *,
        policy: ThermalFanPolicy,
        policy_mode: str,
        thermal_authority: Any,
        history: ThermalObserverHistory,
        runtime_status_provider: Callable[[], dict[str, Any]],
        telemetry_provider: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._policy = policy
        self._policy_mode = policy_mode
        self._thermal_authority = thermal_authority
        self._history = history
        self._runtime_status_provider = runtime_status_provider
        self._telemetry_provider = telemetry_provider
        self._last_signature: tuple[str, bool] | None = None
        self._previous_profile = "automatic"

    @property
    def policy_mode(self) -> str:
        return self._policy_mode

    def observe(
        self,
        telemetry: dict[str, Any] | None = None,
    ) -> Any:
        """Evaluate one recommendation and record changed observer state."""

        if telemetry is None:
            if self._telemetry_provider is None:
                raise RuntimeError(
                    "Host thermal observer requires telemetry"
                )
            telemetry = self._telemetry_provider()

        if self._policy_mode == "disabled":
            recommendation = self._policy.evaluate(
                (),
                telemetry_fresh=False,
            )
        else:
            recommendation = self._policy.evaluate(
                telemetry.get("temperatures_c", ()),
                telemetry_fresh=bool(
                    telemetry.get("telemetry_fresh", False)
                ),
            )

        self._thermal_authority.current_recommendation = recommendation

        signature = (
            recommendation.recommended_profile.value,
            bool(recommendation.telemetry_valid),
        )

        if signature != self._last_signature:
            runtime_status = self._runtime_status_provider()

            try:
                self._history.append(
                    event_from_recommendation(
                        recommendation,
                        active_profile=runtime_status.get(
                            "active_profile",
                            "automatic",
                        ),
                        control_authority=runtime_status.get(
                            "control_authority",
                            "automatic",
                        ),
                        policy_mode=self._policy_mode,
                        previous_recommended_profile=(
                            self._previous_profile
                        ),
                    )
                )
            except Exception:
                LOGGER.exception(
                    "Could not append thermal observer history"
                )

            self._last_signature = signature
            self._previous_profile = (
                recommendation.recommended_profile.value
            )

        return recommendation


__all__ = ["HostThermalObserver"]
