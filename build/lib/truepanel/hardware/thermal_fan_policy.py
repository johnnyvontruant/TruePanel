"""
Observe-only thermal fan policy.

This module recommends an existing guarded TruePanel fan profile from current
temperature telemetry. It performs no hardware writes and does not communicate
with the fan-control executor.

The policy is intentionally stateful so downward hysteresis can prevent rapid
profile changes around temperature thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Callable, Iterable

from truepanel.hardware.fan_control import FanProfile


PROFILE_ORDER = (
    FanProfile.QUIET,
    FanProfile.BALANCED,
    FanProfile.COOLING_BOOST,
    FanProfile.AFTERBURNERS,
)


@dataclass(frozen=True)
class ThermalFanRecommendation:
    """Result produced by the observe-only thermal policy."""

    recommended_profile: FanProfile
    hottest_temperature_c: float | None
    telemetry_valid: bool
    changed: bool
    reason: str


class ThermalFanPolicy:
    """
    Recommend guarded profiles from the hottest available temperature.

    Upward transitions happen immediately at the configured thresholds.
    Downward transitions require the temperature to fall below the next lower
    threshold minus ``hysteresis_c``.

    Invalid or absent telemetry recommends motherboard Automatic rather than a
    manual profile.
    """

    def __init__(
        self,
        *,
        balanced_temperature_c: float = 42.0,
        cooling_boost_temperature_c: float = 50.0,
        afterburners_temperature_c: float = 60.0,
        hysteresis_c: float = 3.0,
        minimum_dwell_seconds: float = 30.0,
        initial_profile: FanProfile | str = FanProfile.AUTOMATIC,
        clock: Callable[[], float] | None = None,
    ):
        thresholds = (
            float(balanced_temperature_c),
            float(cooling_boost_temperature_c),
            float(afterburners_temperature_c),
        )

        if not (
            thresholds[0]
            < thresholds[1]
            < thresholds[2]
        ):
            raise ValueError(
                "Thermal fan thresholds must increase."
            )

        if float(hysteresis_c) < 0:
            raise ValueError(
                "Thermal fan hysteresis cannot be negative."
            )

        if float(minimum_dwell_seconds) < 0:
            raise ValueError(
                "Thermal fan dwell time cannot be negative."
            )

        self.balanced_temperature_c = thresholds[0]
        self.cooling_boost_temperature_c = thresholds[1]
        self.afterburners_temperature_c = thresholds[2]
        self.hysteresis_c = float(hysteresis_c)
        self.minimum_dwell_seconds = float(
            minimum_dwell_seconds
        )
        self.clock = clock or __import__("time").monotonic
        self.current_profile = self._coerce_profile(
            initial_profile
        )
        self.last_change_time = self.clock()

    @staticmethod
    def _coerce_profile(
        profile: FanProfile | str,
    ) -> FanProfile:
        if isinstance(profile, FanProfile):
            return profile

        normalized = str(profile).strip().lower()

        for candidate in FanProfile:
            if candidate.value == normalized:
                return candidate

        raise ValueError(
            f"Unknown fan profile: {profile}"
        )

    @staticmethod
    def _valid_temperatures(
        temperatures_c: Iterable[float | int],
    ) -> list[float]:
        values = []

        for raw_value in temperatures_c or ():
            try:
                value = float(raw_value)
            except (
                TypeError,
                ValueError,
            ):
                continue

            if not isfinite(value):
                continue

            # Reject values that are clearly not plausible hardware telemetry.
            if value < -20.0 or value > 125.0:
                continue

            values.append(value)

        return values

    def _profile_for_temperature(
        self,
        hottest: float,
    ) -> FanProfile:
        if hottest >= self.afterburners_temperature_c:
            return FanProfile.AFTERBURNERS

        if hottest >= self.cooling_boost_temperature_c:
            return FanProfile.COOLING_BOOST

        if hottest >= self.balanced_temperature_c:
            return FanProfile.BALANCED

        return FanProfile.QUIET

    @staticmethod
    def _rank(
        profile: FanProfile,
    ) -> int:
        if profile is FanProfile.AUTOMATIC:
            return -1

        return PROFILE_ORDER.index(profile)

    def _downshift_allowed(
        self,
        *,
        current: FanProfile,
        target: FanProfile,
        hottest: float,
    ) -> bool:
        if current is FanProfile.AFTERBURNERS:
            return (
                hottest
                < self.afterburners_temperature_c
                - self.hysteresis_c
            )

        if current is FanProfile.COOLING_BOOST:
            return (
                hottest
                < self.cooling_boost_temperature_c
                - self.hysteresis_c
            )

        if current is FanProfile.BALANCED:
            return (
                hottest
                < self.balanced_temperature_c
                - self.hysteresis_c
            )

        return True

    def evaluate(
        self,
        temperatures_c: Iterable[float | int],
        *,
        telemetry_fresh: bool = True,
    ) -> ThermalFanRecommendation:
        previous = self.current_profile
        now = self.clock()

        if not telemetry_fresh:
            self.current_profile = FanProfile.AUTOMATIC

            if previous is not FanProfile.AUTOMATIC:
                self.last_change_time = now

            return ThermalFanRecommendation(
                recommended_profile=FanProfile.AUTOMATIC,
                hottest_temperature_c=None,
                telemetry_valid=False,
                changed=(
                    previous
                    is not FanProfile.AUTOMATIC
                ),
                reason=(
                    "Thermal telemetry is stale; "
                    "recommend motherboard automatic control."
                ),
            )

        values = self._valid_temperatures(
            temperatures_c
        )

        if not values:
            self.current_profile = FanProfile.AUTOMATIC

            if previous is not FanProfile.AUTOMATIC:
                self.last_change_time = now

            return ThermalFanRecommendation(
                recommended_profile=FanProfile.AUTOMATIC,
                hottest_temperature_c=None,
                telemetry_valid=False,
                changed=(
                    previous
                    is not FanProfile.AUTOMATIC
                ),
                reason=(
                    "No valid thermal telemetry is available; "
                    "recommend motherboard automatic control."
                ),
            )

        hottest = max(values)
        target = self._profile_for_temperature(
            hottest
        )

        dwell_elapsed = (
            now - self.last_change_time
        )
        dwell_ready = (
            dwell_elapsed
            >= self.minimum_dwell_seconds
        )

        if previous is FanProfile.AUTOMATIC:
            selected = target
        elif self._rank(target) > self._rank(previous):
            selected = target
        elif self._rank(target) < self._rank(previous):
            selected = (
                target
                if (
                    dwell_ready
                    and self._downshift_allowed(
                        current=previous,
                        target=target,
                        hottest=hottest,
                    )
                )
                else previous
            )
        else:
            selected = previous

        self.current_profile = selected
        changed = selected is not previous

        if changed:
            self.last_change_time = now

        if (
            selected is not target
            and not dwell_ready
        ):
            remaining = max(
                0.0,
                self.minimum_dwell_seconds
                - dwell_elapsed,
            )
            reason = (
                f"Holding {selected.value} at "
                f"{hottest:.1f}°C for "
                f"{remaining:.1f}s minimum dwell."
            )
        elif selected is not target:
            reason = (
                f"Holding {selected.value} at "
                f"{hottest:.1f}°C until downward "
                f"hysteresis clears."
            )
        elif changed:
            reason = (
                f"Thermal recommendation changed to "
                f"{selected.value} at {hottest:.1f}°C."
            )
        else:
            reason = (
                f"Thermal recommendation remains "
                f"{selected.value} at {hottest:.1f}°C."
            )

        return ThermalFanRecommendation(
            recommended_profile=selected,
            hottest_temperature_c=hottest,
            telemetry_valid=True,
            changed=changed,
            reason=reason,
        )


__all__ = [
    "ThermalFanPolicy",
    "ThermalFanRecommendation",
]
