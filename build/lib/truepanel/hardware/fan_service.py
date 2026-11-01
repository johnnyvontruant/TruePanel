"""
Safety orchestration for TruePanel fan control.

This service combines the policy interlock with the bounded hardware executor.
It owns profile state, command expiry, safety reconciliation, and shutdown
restoration. The web interface must never access sysfs directly.
"""

import logging
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from truepanel.hardware.fan_control import (
    FanControlDecision,
    FanControlInterlock,
    FanProfile,
)
from truepanel.hardware.fan_executor import (
    FanHardwareExecutor,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FanControlStatus:
    active_profile: FanProfile
    requested_profile: FanProfile
    expires_at: float | None
    remaining_seconds: float | None
    last_reason: str
    closed: bool
    control_authority: str
    safety_hold: bool
    recovery_pending: bool
    recovery_healthy_cycles: int
    recovery_required_cycles: int


class FanControlService:
    """
    Coordinate profile requests and continuous safety enforcement.

    Normal manual profiles expire back to Automatic. Manually requested
    Afterburners uses a separate timeout, while safety-forced Afterburners
    remains active until the emergency condition is explicitly cleared.
    """

    def __init__(
        self,
        interlock: FanControlInterlock,
        executor: FanHardwareExecutor,
        *,
        command_timeout: float = 300.0,
        afterburners_timeout: float = 120.0,
        safety_recovery_cycles: int = 3,
        profile_timeouts: Mapping | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.interlock = interlock
        self.executor = executor
        self.command_timeout = max(
            0.0,
            float(command_timeout),
        )
        self.afterburners_timeout = max(
            0.0,
            float(afterburners_timeout),
        )
        self.safety_recovery_cycles = max(
            1,
            int(safety_recovery_cycles),
        )

        self.profile_timeouts = {
            FanProfile.QUIET: (
                self.command_timeout
            ),
            FanProfile.BALANCED: (
                self.command_timeout
            ),
            FanProfile.COOLING_BOOST: (
                self.command_timeout
            ),
            FanProfile.AFTERBURNERS: (
                self.afterburners_timeout
            ),
        }

        for raw_profile, raw_timeout in (
            profile_timeouts
            or {}
        ).items():
            try:
                profile = (
                    self.interlock
                    .normalize_profile(
                        raw_profile
                    )
                )
                timeout = max(
                    0.0,
                    float(
                        raw_timeout
                    ),
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            if profile is not FanProfile.AUTOMATIC:
                self.profile_timeouts[
                    profile
                ] = timeout

        self.clock = clock

        self.active_profile = FanProfile.AUTOMATIC
        self.requested_profile = FanProfile.AUTOMATIC
        self.expires_at: float | None = None
        self.last_reason = (
            "Motherboard automatic control active."
        )
        self._safety_recovery_count = 0
        self._closed = False

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError(
                "Fan control service is closed."
            )

    def _set_state(
        self,
        decision: FanControlDecision,
        *,
        manual_request: bool = False,
    ) -> None:
        now = self.clock()

        self.requested_profile = (
            decision.requested_profile
        )
        self.active_profile = (
            decision.effective_profile
        )
        self.last_reason = decision.reason

        if (
            decision.effective_profile
            is FanProfile.AUTOMATIC
        ):
            self.expires_at = None
            return

        if not manual_request:
            self.expires_at = None
            return

        manual_afterburners = (
            decision.requested_profile
            is FanProfile.AFTERBURNERS
            and decision.effective_profile
            is FanProfile.AFTERBURNERS
        )

        safety_afterburners = (
            decision.effective_profile
            is FanProfile.AFTERBURNERS
            and not manual_afterburners
        )

        if safety_afterburners:
            self.expires_at = None
            return

        timeout = self.profile_timeouts.get(
            decision.effective_profile,
            self.command_timeout,
        )

        if timeout > 0:
            self.expires_at = (
                now
                + timeout
            )
        else:
            self.expires_at = None

    def request_profile(
        self,
        profile: FanProfile | str,
        *,
        fan_status: Mapping,
        temperatures_c: Sequence[int | float],
        telemetry_fresh: bool = True,
    ) -> FanControlDecision:
        """
        Validate and apply a requested profile.

        Even rejected requests may produce a mandatory safety action such as
        returning to Automatic or engaging Afterburners.
        """

        self._ensure_open()

        decision = self.interlock.evaluate(
            profile,
            fan_status=fan_status,
            temperatures_c=temperatures_c,
            telemetry_fresh=telemetry_fresh,
        )

        self.executor.apply(
            decision
        )
        self._set_state(
            decision,
            manual_request=True,
        )

        LOGGER.info(
            "Fan profile request %s resulted in %s: %s",
            decision.requested_profile.value,
            decision.effective_profile.value,
            decision.reason,
        )

        return decision

    def _expire_if_needed(
        self,
    ) -> bool:
        if self.expires_at is None:
            return False

        if self.clock() < self.expires_at:
            return False

        decision = FanControlDecision(
            accepted=True,
            requested_profile=FanProfile.AUTOMATIC,
            effective_profile=FanProfile.AUTOMATIC,
            pwm=None,
            reason=(
                "Manual fan-control command expired; "
                "returning to Automatic."
            ),
            force_automatic=True,
        )

        self.executor.apply(
            decision
        )
        self._set_state(
            decision
        )

        LOGGER.warning(
            "Fan-control dead-man timeout restored Automatic mode"
        )

        return True

    def reconcile(
        self,
        *,
        fan_status: Mapping,
        temperatures_c: Sequence[int | float],
        telemetry_fresh: bool = True,
    ) -> FanControlDecision | None:
        """
        Re-evaluate active control against current telemetry.

        Automatic remains untouched while healthy. Emergency conditions may
        engage Afterburners from any state. Manual profiles fall back to
        Automatic when telemetry becomes stale or temperatures become unsafe.
        """

        self._ensure_open()

        evaluation_profile = self.active_profile

        if evaluation_profile in (
            FanProfile.AUTOMATIC,
            FanProfile.AFTERBURNERS,
        ):
            # Probe safety with a controllable manual profile. A healthy
            # result must not replace Automatic or an active Afterburners
            # command.
            evaluation_profile = FanProfile.BALANCED

        decision = self.interlock.evaluate(
            evaluation_profile,
            fan_status=fan_status,
            temperatures_c=temperatures_c,
            telemetry_fresh=telemetry_fresh,
        )

        if (
            decision.effective_profile
            is FanProfile.AFTERBURNERS
        ):
            self._safety_recovery_count = 0

            if (
                self.active_profile
                is FanProfile.AFTERBURNERS
            ):
                if self.expires_at is None:
                    # Safety already owns Afterburners. Avoid duplicate
                    # decisions and repeated PWM writes.
                    return None

                # Convert timed manual Afterburners into an unlimited
                # safety hold without writing the same PWM again.
                self._set_state(
                    decision
                )

                LOGGER.warning(
                    "Manual Afterburners converted to safety hold: %s",
                    decision.reason,
                )

                return decision

            self.executor.apply(
                decision
            )
            self._set_state(
                decision
            )

            LOGGER.warning(
                "Fan safety reconciliation changed profile to %s: %s",
                decision.effective_profile.value,
                decision.reason,
            )

            return decision

        if self.active_profile is FanProfile.AFTERBURNERS:
            if self.expires_at is not None:
                if self._expire_if_needed():
                    return FanControlDecision(
                        accepted=True,
                        requested_profile=FanProfile.AUTOMATIC,
                        effective_profile=FanProfile.AUTOMATIC,
                        pwm=None,
                        reason=self.last_reason,
                        force_automatic=True,
                    )

                return None

            if not telemetry_fresh:
                self._safety_recovery_count = 0
                self.last_reason = (
                    "Safety recovery paused because "
                    "telemetry is stale."
                )
                return None

            self._safety_recovery_count += 1

            if (
                self._safety_recovery_count
                < self.safety_recovery_cycles
            ):
                self.last_reason = (
                    "Safety recovery telemetry healthy "
                    f"({self._safety_recovery_count}/"
                    f"{self.safety_recovery_cycles})."
                )
                return None

            recovery = FanControlDecision(
                accepted=True,
                requested_profile=FanProfile.AUTOMATIC,
                effective_profile=FanProfile.AUTOMATIC,
                pwm=None,
                reason=(
                    "Safety recovery confirmed after "
                    f"{self.safety_recovery_cycles} "
                    "healthy telemetry cycles; "
                    "returning to Automatic."
                ),
                force_automatic=True,
            )

            self.executor.apply(
                recovery
            )
            self._set_state(
                recovery
            )
            self._safety_recovery_count = 0

            LOGGER.warning(
                "Fan safety hold cleared after %s healthy cycles",
                self.safety_recovery_cycles,
            )

            return recovery

        if self._expire_if_needed():
            return FanControlDecision(
                accepted=True,
                requested_profile=FanProfile.AUTOMATIC,
                effective_profile=FanProfile.AUTOMATIC,
                pwm=None,
                reason=self.last_reason,
                force_automatic=True,
            )

        if self.active_profile is FanProfile.AUTOMATIC:
            if (
                decision.effective_profile
                is not FanProfile.AFTERBURNERS
            ):
                return None
        else:
            if (
                decision.accepted
                and decision.effective_profile
                is self.active_profile
            ):
                return None

        self.executor.apply(
            decision
        )
        self._set_state(
            decision
        )

        LOGGER.warning(
            "Fan safety reconciliation changed profile to %s: %s",
            decision.effective_profile.value,
            decision.reason,
        )

        return decision

    def tick(
        self,
        *,
        fan_status: Mapping,
        temperatures_c: Sequence[int | float],
        telemetry_fresh: bool = True,
    ) -> FanControlDecision | None:
        """Run one dead-man and safety evaluation cycle."""

        return self.reconcile(
            fan_status=fan_status,
            temperatures_c=temperatures_c,
            telemetry_fresh=telemetry_fresh,
        )

    def status(
        self,
    ) -> FanControlStatus:
        remaining = None

        if self.expires_at is not None:
            remaining = max(
                0.0,
                self.expires_at
                - self.clock(),
            )

        safety_hold = (
            self.active_profile
            is FanProfile.AFTERBURNERS
            and self.expires_at is None
        )

        if safety_hold:
            control_authority = "safety"
        elif (
            self.active_profile
            is FanProfile.AUTOMATIC
        ):
            control_authority = "automatic"
        else:
            control_authority = "manual"

        recovery_count = int(
            self._safety_recovery_count
        )

        return FanControlStatus(
            active_profile=self.active_profile,
            requested_profile=self.requested_profile,
            expires_at=self.expires_at,
            remaining_seconds=remaining,
            last_reason=self.last_reason,
            closed=self._closed,
            control_authority=control_authority,
            safety_hold=safety_hold,
            recovery_pending=bool(
                safety_hold
                and recovery_count > 0
            ),
            recovery_healthy_cycles=(
                recovery_count
            ),
            recovery_required_cycles=(
                self.safety_recovery_cycles
            ),
        )

    def shutdown(self) -> None:
        if self._closed:
            return

        try:
            self.executor.close()
        finally:
            self.active_profile = (
                FanProfile.AUTOMATIC
            )
            self.requested_profile = (
                FanProfile.AUTOMATIC
            )
            self.expires_at = None
            self.last_reason = (
                "Fan control service shut down; "
                "Automatic restoration requested."
            )
            self._closed = True

        LOGGER.info(
            "Fan control service shut down"
        )

    def __enter__(
        self,
    ):
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        self.shutdown()
        return False


__all__ = [
    "FanControlService",
    "FanControlStatus",
]
