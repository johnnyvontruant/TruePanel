"""
Safety-gated fan-control policy for TruePanel.

This module contains no direct hardware writes. It validates requested fan
profiles and produces decisions that a separate hardware executor may apply.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence


class FanProfile(str, Enum):
    AUTOMATIC = "automatic"
    QUIET = "quiet"
    BALANCED = "balanced"
    COOLING_BOOST = "cooling_boost"
    AFTERBURNERS = "afterburners"


PROFILE_PWM = {
    FanProfile.AUTOMATIC: None,
    FanProfile.QUIET: 170,
    FanProfile.BALANCED: 194,
    FanProfile.COOLING_BOOST: 225,
    FanProfile.AFTERBURNERS: 255,
}


@dataclass(frozen=True)
class FanControlDecision:
    accepted: bool
    requested_profile: FanProfile
    effective_profile: FanProfile
    pwm: int | None
    reason: str
    force_automatic: bool = False


class FanControlInterlock:
    """
    Validate fan-profile requests without touching hardware.

    The interlock fails toward Automatic or Afterburners depending on the
    failure mode. Missing telemetry prevents quieter manual profiles, while
    excessive temperature forces maximum cooling.
    """

    def __init__(
        self,
        *,
        controlled_channels: Sequence[int] = (1, 2),
        minimum_rpm: int = 300,
        maximum_temperature_c: int = 65,
        emergency_temperature_c: int = 75,
        minimum_manual_pwm: int = 170,
        profile_pwm: Mapping | None = None,
    ):
        self.controlled_channels = tuple(
            int(channel)
            for channel in controlled_channels
        )
        self.minimum_rpm = max(
            1,
            int(minimum_rpm),
        )
        self.maximum_temperature_c = int(
            maximum_temperature_c
        )
        self.emergency_temperature_c = int(
            emergency_temperature_c
        )
        self.minimum_manual_pwm = max(
            0,
            min(
                255,
                int(minimum_manual_pwm),
            ),
        )

        self.profile_pwm = dict(
            PROFILE_PWM
        )

        for raw_profile, raw_pwm in (
            profile_pwm
            or {}
        ).items():
            try:
                profile = self.normalize_profile(
                    raw_profile
                )
                pwm = int(
                    raw_pwm
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            if profile in (
                FanProfile.AUTOMATIC,
                FanProfile.AFTERBURNERS,
            ):
                continue

            self.profile_pwm[
                profile
            ] = max(
                self.minimum_manual_pwm,
                min(
                    255,
                    pwm,
                ),
            )

        # Emergency cooling is deliberately immutable.
        self.profile_pwm[
            FanProfile.AFTERBURNERS
        ] = 255

        if (
            self.emergency_temperature_c
            <= self.maximum_temperature_c
        ):
            raise ValueError(
                "Emergency temperature must exceed "
                "maximum operating temperature."
            )

    @staticmethod
    def normalize_profile(
        profile: FanProfile | str,
    ) -> FanProfile:
        if isinstance(
            profile,
            FanProfile,
        ):
            return profile

        normalized = str(profile).strip().lower()

        aliases = {
            "auto": FanProfile.AUTOMATIC,
            "automatic": FanProfile.AUTOMATIC,
            "quiet": FanProfile.QUIET,
            "balanced": FanProfile.BALANCED,
            "boost": FanProfile.COOLING_BOOST,
            "cooling boost": FanProfile.COOLING_BOOST,
            "cooling_boost": FanProfile.COOLING_BOOST,
            "afterburners": FanProfile.AFTERBURNERS,
            "full": FanProfile.AFTERBURNERS,
        }

        try:
            return aliases[normalized]
        except KeyError as error:
            raise ValueError(
                f"Unknown fan profile: {profile}"
            ) from error

    def evaluate(
        self,
        profile: FanProfile | str,
        *,
        fan_status: Mapping,
        temperatures_c: Sequence[int | float],
        telemetry_fresh: bool = True,
    ) -> FanControlDecision:
        requested = self.normalize_profile(
            profile
        )

        if requested is FanProfile.AFTERBURNERS:
            return FanControlDecision(
                accepted=True,
                requested_profile=requested,
                effective_profile=FanProfile.AFTERBURNERS,
                pwm=255,
                reason="Afterburners requested.",
            )

        if requested is FanProfile.AUTOMATIC:
            return FanControlDecision(
                accepted=True,
                requested_profile=requested,
                effective_profile=FanProfile.AUTOMATIC,
                pwm=None,
                reason="Returning control to motherboard automatic mode.",
                force_automatic=True,
            )

        if not telemetry_fresh:
            return FanControlDecision(
                accepted=False,
                requested_profile=requested,
                effective_profile=FanProfile.AUTOMATIC,
                pwm=None,
                reason="Fan telemetry is stale.",
                force_automatic=True,
            )

        temperatures = [
            float(value)
            for value in temperatures_c
        ]

        if not temperatures:
            return FanControlDecision(
                accepted=False,
                requested_profile=requested,
                effective_profile=FanProfile.AUTOMATIC,
                pwm=None,
                reason="Temperature telemetry is unavailable.",
                force_automatic=True,
            )

        hottest = max(
            temperatures
        )

        if hottest >= self.emergency_temperature_c:
            return FanControlDecision(
                accepted=True,
                requested_profile=requested,
                effective_profile=FanProfile.AFTERBURNERS,
                pwm=255,
                reason=(
                    f"Emergency temperature reached: "
                    f"{hottest:.1f}°C."
                ),
            )

        if hottest >= self.maximum_temperature_c:
            return FanControlDecision(
                accepted=False,
                requested_profile=requested,
                effective_profile=FanProfile.AUTOMATIC,
                pwm=None,
                reason=(
                    f"Manual profile blocked at "
                    f"{hottest:.1f}°C."
                ),
                force_automatic=True,
            )

        channels = {
            int(channel.get("number", 0)): channel
            for channel in fan_status.get(
                "fan_channels",
                []
            )
        }

        for channel_number in self.controlled_channels:
            channel = channels.get(
                channel_number
            )

            if channel is None:
                return FanControlDecision(
                    accepted=False,
                    requested_profile=requested,
                    effective_profile=FanProfile.AUTOMATIC,
                    pwm=None,
                    reason=(
                        f"Fan channel {channel_number} "
                        "telemetry is unavailable."
                    ),
                    force_automatic=True,
                )

            rpm = int(
                channel.get(
                    "rpm",
                    0,
                )
            )

            alarm = channel.get(
                "alarm"
            )

            if alarm is True or rpm < self.minimum_rpm:
                return FanControlDecision(
                    accepted=False,
                    requested_profile=requested,
                    effective_profile=FanProfile.AFTERBURNERS,
                    pwm=255,
                    reason=(
                        f"Fan channel {channel_number} "
                        f"is unhealthy at {rpm} RPM."
                    ),
                )

        pwm = self.profile_pwm[
            requested
        ]

        if pwm is None:
            raise RuntimeError(
                "Manual profile unexpectedly lacks PWM."
            )

        pwm = max(
            self.minimum_manual_pwm,
            int(pwm),
        )

        return FanControlDecision(
            accepted=True,
            requested_profile=requested,
            effective_profile=requested,
            pwm=pwm,
            reason="Manual fan profile accepted.",
        )


__all__ = [
    "FanControlDecision",
    "FanControlInterlock",
    "FanProfile",
    "PROFILE_PWM",
]
