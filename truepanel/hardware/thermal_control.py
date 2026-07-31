"""
Safety-gated automatic thermal fan-control coordination.

This module connects a ThermalFanPolicy recommendation to the existing
FanControlService. It contains no hardware implementation and performs no
work merely by being imported.

Automatic control requires both:

* thermal policy mode ``automatic_control``
* explicit operator arming

The coordinator suppresses duplicate requests, returns control to the
motherboard when an owned session becomes unsafe or disarmed, and delegates
every actual profile transition to FanControlService and its interlock.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from truepanel.hardware.fan_control import (
    FanControlDecision,
    FanProfile,
)
from truepanel.hardware.fan_status_bridge import (
    thermal_control_readiness,
)


_PROFILE_RANK = {
    FanProfile.AUTOMATIC: 0,
    FanProfile.QUIET: 1,
    FanProfile.BALANCED: 2,
    FanProfile.COOLING_BOOST: 3,
    FanProfile.AFTERBURNERS: 4,
}


@dataclass(frozen=True)
class ThermalControlResult:
    """
    Result of one automatic-control evaluation cycle.

    ``decision`` is populated only when the existing FanControlService was
    asked to perform a transition.
    """

    state: str
    requested_profile: FanProfile | None
    decision: FanControlDecision | None
    readiness: Mapping[str, Any]
    reason: str
    owns_control: bool
    cooldown_remaining: float = 0.0


class ThermalControlCoordinator:
    """
    Coordinate automatic thermal recommendations through FanControlService.

    The coordinator intentionally does not know how PWM is written. All
    transitions pass through ``service.request_profile()``, preserving the
    existing interlock, hardware executor, history, and safety behavior.
    """

    def __init__(
        self,
        service,
        *,
        policy_mode: str = "observe_only",
        operator_armed: bool = False,
        dry_run: bool = True,
        command_cooldown_seconds: float = 30.0,
        clock: Callable[[], float] | None = None,
    ):
        if float(command_cooldown_seconds) < 0:
            raise ValueError(
                "Thermal command cooldown cannot be negative."
            )

        self.service = service
        self.policy_mode = str(
            policy_mode
        ).strip().lower()
        self.operator_armed = bool(
            operator_armed
        )
        self.dry_run = bool(
            dry_run
        )
        self.command_cooldown_seconds = float(
            command_cooldown_seconds
        )
        self.clock = clock or time.monotonic

        self.owns_control = False
        self.last_requested_profile: FanProfile | None = None
        self.last_command_at: float | None = None
        self.simulated_profile = FanProfile.AUTOMATIC

    @staticmethod
    def _profile(
        value: FanProfile | str,
    ) -> FanProfile:
        if isinstance(value, FanProfile):
            return value

        return FanProfile(
            str(value).strip().lower()
        )

    def configure(
        self,
        *,
        policy_mode: str | None = None,
        operator_armed: bool | None = None,
        dry_run: bool | None = None,
    ) -> None:
        """Update runtime arming configuration without actuating hardware."""

        if policy_mode is not None:
            self.policy_mode = str(
                policy_mode
            ).strip().lower()

        if operator_armed is not None:
            self.operator_armed = bool(
                operator_armed
            )

        if dry_run is not None:
            self.dry_run = bool(
                dry_run
            )

    def _cooldown_remaining(
        self,
    ) -> float:
        if self.last_command_at is None:
            return 0.0

        return max(
            0.0,
            self.command_cooldown_seconds
            - (
                float(self.clock())
                - self.last_command_at
            ),
        )

    @staticmethod
    def _runtime_value(
        runtime_status: Mapping[str, Any],
        name: str,
        default: Any,
    ) -> Any:
        return runtime_status.get(
            name,
            default,
        )

    def _readiness(
        self,
        *,
        runtime_status: Mapping[str, Any],
        recommendation,
    ) -> dict[str, Any]:
        return thermal_control_readiness(
            policy_mode=self.policy_mode,
            connected=bool(
                self._runtime_value(
                    runtime_status,
                    "connected",
                    False,
                )
            ),
            telemetry_valid=bool(
                recommendation.telemetry_valid
            ),
            safety_hold=bool(
                self._runtime_value(
                    runtime_status,
                    "safety_hold",
                    False,
                )
            ),
            recovery_pending=bool(
                self._runtime_value(
                    runtime_status,
                    "recovery_pending",
                    False,
                )
            ),
            recommended_profile=(
                recommendation
                .recommended_profile
                .value
            ),
            operator_armed=(
                self.operator_armed
            ),
        )

    def _request(
        self,
        profile: FanProfile,
        *,
        telemetry: Mapping[str, Any],
    ) -> FanControlDecision:
        decision = self.service.request_profile(
            profile,
            fan_status=telemetry.get(
                "fan_status",
                {},
            ),
            temperatures_c=telemetry.get(
                "temperatures_c",
                (),
            ),
            telemetry_fresh=bool(
                telemetry.get(
                    "telemetry_fresh",
                    False,
                )
            ),
        )

        self.last_requested_profile = profile
        self.last_command_at = float(
            self.clock()
        )

        self.owns_control = (
            decision.effective_profile
            is not FanProfile.AUTOMATIC
        )

        return decision

    def _release_to_automatic(
        self,
        *,
        telemetry: Mapping[str, Any],
        readiness: Mapping[str, Any],
        reason: str,
    ) -> ThermalControlResult:
        decision = self._request(
            FanProfile.AUTOMATIC,
            telemetry=telemetry,
        )

        self.owns_control = False

        return ThermalControlResult(
            state="released",
            requested_profile=(
                FanProfile.AUTOMATIC
            ),
            decision=decision,
            readiness=readiness,
            reason=reason,
            owns_control=False,
        )

    def evaluate(
        self,
        recommendation,
        *,
        telemetry: Mapping[str, Any],
        runtime_status: Mapping[str, Any],
    ) -> ThermalControlResult:
        """
        Evaluate and optionally apply one automatic thermal transition.

        Upshifts are never delayed by command cooldown. Downshifts are already
        protected by ThermalFanPolicy hysteresis and dwell time, then receive
        this additional command-level cooldown.
        """

        readiness = self._readiness(
            runtime_status=runtime_status,
            recommendation=recommendation,
        )

        active_profile = self._profile(
            self._runtime_value(
                runtime_status,
                "active_profile",
                FanProfile.AUTOMATIC.value,
            )
        )

        recommended_profile = (
            recommendation.recommended_profile
        )

        if not readiness["armed"]:
            if (
                self.dry_run
                and self.simulated_profile
                is not FanProfile.AUTOMATIC
            ):
                self.simulated_profile = (
                    FanProfile.AUTOMATIC
                )
                self.last_requested_profile = (
                    FanProfile.AUTOMATIC
                )
                self.last_command_at = float(
                    self.clock()
                )
                self.owns_control = False

                return ThermalControlResult(
                    state="simulated",
                    requested_profile=(
                        FanProfile.AUTOMATIC
                    ),
                    decision=None,
                    readiness=readiness,
                    reason=(
                        "Dry run simulated returning "
                        "to motherboard automatic "
                        "control because thermal "
                        "readiness became blocked."
                    ),
                    owns_control=False,
                )

            if (
                self.owns_control
                and active_profile
                is not FanProfile.AUTOMATIC
            ):
                return self._release_to_automatic(
                    telemetry=telemetry,
                    readiness=readiness,
                    reason=(
                        "Automatic thermal control "
                        "became unavailable; returning "
                        "control to the motherboard."
                    ),
                )

            self.owns_control = False
            self.simulated_profile = (
                FanProfile.AUTOMATIC
            )

            return ThermalControlResult(
                state="blocked",
                requested_profile=None,
                decision=None,
                readiness=readiness,
                reason=(
                    readiness["blocking_reasons"][0]
                    if readiness[
                        "blocking_reasons"
                    ]
                    else (
                        "Automatic thermal control "
                        "is not armed."
                    )
                ),
                owns_control=False,
            )

        comparison_profile = (
            self.simulated_profile
            if self.dry_run
            else active_profile
        )

        if (
            recommended_profile
            is FanProfile.AUTOMATIC
        ):
            if self.dry_run:
                if (
                    self.simulated_profile
                    is not FanProfile.AUTOMATIC
                ):
                    self.simulated_profile = (
                        FanProfile.AUTOMATIC
                    )
                    self.last_requested_profile = (
                        FanProfile.AUTOMATIC
                    )
                    self.last_command_at = float(
                        self.clock()
                    )

                    return ThermalControlResult(
                        state="simulated",
                        requested_profile=(
                            FanProfile.AUTOMATIC
                        ),
                        decision=None,
                        readiness=readiness,
                        reason=(
                            "Dry run simulated returning "
                            "to motherboard automatic "
                            "control."
                        ),
                        owns_control=False,
                    )

                return ThermalControlResult(
                    state="aligned",
                    requested_profile=None,
                    decision=None,
                    readiness=readiness,
                    reason=(
                        "Dry-run profile already matches "
                        "motherboard automatic control."
                    ),
                    owns_control=False,
                )

            if (
                self.owns_control
                or active_profile
                is not FanProfile.AUTOMATIC
            ):
                return self._release_to_automatic(
                    telemetry=telemetry,
                    readiness=readiness,
                    reason=(
                        "Thermal telemetry requires "
                        "motherboard automatic control."
                    ),
                )

            return ThermalControlResult(
                state="aligned",
                requested_profile=None,
                decision=None,
                readiness=readiness,
                reason=(
                    "Motherboard automatic control "
                    "already matches the thermal policy."
                ),
                owns_control=False,
            )

        if comparison_profile is recommended_profile:
            self.last_requested_profile = (
                recommended_profile
            )

            if not self.dry_run:
                self.owns_control = True

            return ThermalControlResult(
                state="aligned",
                requested_profile=None,
                decision=None,
                readiness=readiness,
                reason=(
                    "Simulated fan profile already matches "
                    "the thermal recommendation."
                    if self.dry_run
                    else (
                        "Active fan profile already matches "
                        "the thermal recommendation."
                    )
                ),
                owns_control=(
                    False
                    if self.dry_run
                    else True
                ),
            )

        cooldown_remaining = (
            self._cooldown_remaining()
        )

        is_upshift = (
            _PROFILE_RANK[
                recommended_profile
            ]
            > _PROFILE_RANK[
                comparison_profile
            ]
        )

        if (
            cooldown_remaining > 0
            and not is_upshift
        ):
            return ThermalControlResult(
                state="cooldown",
                requested_profile=None,
                decision=None,
                readiness=readiness,
                reason=(
                    "Thermal profile downshift is "
                    "waiting for command cooldown."
                ),
                owns_control=(
                    self.owns_control
                ),
                cooldown_remaining=(
                    cooldown_remaining
                ),
            )

        if self.dry_run:
            self.simulated_profile = (
                recommended_profile
            )
            self.last_requested_profile = (
                recommended_profile
            )
            self.last_command_at = float(
                self.clock()
            )
            self.owns_control = False

            return ThermalControlResult(
                state="simulated",
                requested_profile=(
                    recommended_profile
                ),
                decision=None,
                readiness=readiness,
                reason=(
                    "Dry run simulated thermal profile "
                    f"{recommended_profile.value}."
                ),
                owns_control=False,
            )

        decision = self._request(
            recommended_profile,
            telemetry=telemetry,
        )

        return ThermalControlResult(
            state=(
                "applied"
                if decision.accepted
                else "safety_override"
            ),
            requested_profile=(
                recommended_profile
            ),
            decision=decision,
            readiness=readiness,
            reason=decision.reason,
            owns_control=(
                self.owns_control
            ),
        )


__all__ = [
    "ThermalControlCoordinator",
    "ThermalControlResult",
]
