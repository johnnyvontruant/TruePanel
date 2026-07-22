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


class FanControlService:
    """
    Coordinate profile requests and continuous safety enforcement.

    Normal manual profiles expire back to Automatic. Afterburners remains
    active until explicitly changed because it is always a safe cooling state.
    """

    def __init__(
        self,
        interlock: FanControlInterlock,
        executor: FanHardwareExecutor,
        *,
        command_timeout: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.interlock = interlock
        self.executor = executor
        self.command_timeout = max(
            0.0,
            float(command_timeout),
        )
        self.clock = clock

        self.active_profile = FanProfile.AUTOMATIC
        self.requested_profile = FanProfile.AUTOMATIC
        self.expires_at: float | None = None
        self.last_reason = (
            "Motherboard automatic control active."
        )
        self._closed = False

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError(
                "Fan control service is closed."
            )

    def _set_state(
        self,
        decision: FanControlDecision,
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
            in (
                FanProfile.AUTOMATIC,
                FanProfile.AFTERBURNERS,
            )
            or self.command_timeout <= 0
        ):
            self.expires_at = None
        else:
            self.expires_at = (
                now
                + self.command_timeout
            )

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
            decision
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

        if self._expire_if_needed():
            return FanControlDecision(
                accepted=True,
                requested_profile=FanProfile.AUTOMATIC,
                effective_profile=FanProfile.AUTOMATIC,
                pwm=None,
                reason=self.last_reason,
                force_automatic=True,
            )

        if self.active_profile is FanProfile.AFTERBURNERS:
            return None

        evaluation_profile = self.active_profile

        if evaluation_profile is FanProfile.AUTOMATIC:
            # Use a manual profile only as a safety probe. A healthy result
            # must not be applied because motherboard control remains active.
            evaluation_profile = FanProfile.BALANCED

        decision = self.interlock.evaluate(
            evaluation_profile,
            fan_status=fan_status,
            temperatures_c=temperatures_c,
            telemetry_fresh=telemetry_fresh,
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

        return FanControlStatus(
            active_profile=self.active_profile,
            requested_profile=self.requested_profile,
            expires_at=self.expires_at,
            remaining_seconds=remaining,
            last_reason=self.last_reason,
            closed=self._closed,
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
