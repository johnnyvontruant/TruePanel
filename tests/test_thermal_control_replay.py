"""End-to-end synthetic replay tests for thermal fan control.

These tests exercise the production thermal policy and coordinator together
while guaranteeing that dry-run mode cannot reach the hardware service.
"""

from dataclasses import dataclass

from truepanel.hardware.fan_control import FanProfile
from truepanel.hardware.thermal_control import (
    ThermalControlCoordinator,
)
from truepanel.hardware.thermal_fan_policy import (
    ThermalFanPolicy,
)


class FakeClock:
    """Deterministic monotonic clock for dwell and cooldown testing."""

    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += float(seconds)


class NoHardwareService:
    """Fail immediately if dry-run reaches the fan-control service."""

    def __init__(self):
        self.requests = []

    def request_profile(self, *args, **kwargs):
        self.requests.append(
            {
                "args": args,
                "kwargs": kwargs,
            }
        )

        raise AssertionError(
            "Dry-run replay reached the hardware service."
        )


@dataclass(frozen=True)
class ReplayStep:
    name: str
    advance: float
    temperature: float | None
    telemetry_fresh: bool
    expected_recommendation: FanProfile
    expected_simulated: FanProfile
    expected_state: str


def test_complete_dry_run_thermal_replay():
    """Validate the complete profile ladder without hardware access."""

    clock = FakeClock()
    service = NoHardwareService()

    policy = ThermalFanPolicy(
        balanced_temperature_c=42,
        cooling_boost_temperature_c=50,
        afterburners_temperature_c=60,
        hysteresis_c=3,
        minimum_dwell_seconds=30,
        clock=clock,
    )

    coordinator = ThermalControlCoordinator(
        service,
        policy_mode="automatic_control",
        operator_armed=True,
        dry_run=True,
        command_cooldown_seconds=30,
        clock=clock,
    )

    telemetry = {
        "fan_status": {
            "fan_channels": [
                {
                    "number": 1,
                    "rpm": 1900,
                    "alarm": False,
                },
                {
                    "number": 2,
                    "rpm": 1850,
                    "alarm": False,
                },
            ]
        },
        "temperatures_c": (),
        "telemetry_fresh": True,
    }

    runtime_status = {
        "connected": True,
        "active_profile": "automatic",
        "safety_hold": False,
        "recovery_pending": False,
    }

    steps = [
        ReplayStep(
            name="normal baseline",
            advance=0,
            temperature=47,
            telemetry_fresh=True,
            expected_recommendation=FanProfile.BALANCED,
            expected_simulated=FanProfile.BALANCED,
            expected_state="simulated",
        ),
        ReplayStep(
            name="approach cooling threshold",
            advance=5,
            temperature=49,
            telemetry_fresh=True,
            expected_recommendation=FanProfile.BALANCED,
            expected_simulated=FanProfile.BALANCED,
            expected_state="aligned",
        ),
        ReplayStep(
            name="cross cooling threshold",
            advance=5,
            temperature=50,
            telemetry_fresh=True,
            expected_recommendation=FanProfile.COOLING_BOOST,
            expected_simulated=FanProfile.COOLING_BOOST,
            expected_state="simulated",
        ),
        ReplayStep(
            name="cooling hysteresis hold",
            advance=10,
            temperature=49,
            telemetry_fresh=True,
            expected_recommendation=FanProfile.COOLING_BOOST,
            expected_simulated=FanProfile.COOLING_BOOST,
            expected_state="aligned",
        ),
        ReplayStep(
            name="cooling dwell hold",
            advance=5,
            temperature=46,
            telemetry_fresh=True,
            expected_recommendation=FanProfile.COOLING_BOOST,
            expected_simulated=FanProfile.COOLING_BOOST,
            expected_state="aligned",
        ),
        ReplayStep(
            name="release to balanced",
            advance=20,
            temperature=46,
            telemetry_fresh=True,
            expected_recommendation=FanProfile.BALANCED,
            expected_simulated=FanProfile.BALANCED,
            expected_state="simulated",
        ),
        ReplayStep(
            name="balanced hysteresis hold",
            advance=30,
            temperature=40,
            telemetry_fresh=True,
            expected_recommendation=FanProfile.BALANCED,
            expected_simulated=FanProfile.BALANCED,
            expected_state="aligned",
        ),
        ReplayStep(
            name="release to quiet",
            advance=1,
            temperature=38,
            telemetry_fresh=True,
            expected_recommendation=FanProfile.QUIET,
            expected_simulated=FanProfile.QUIET,
            expected_state="simulated",
        ),
        ReplayStep(
            name="emergency afterburners upshift",
            advance=1,
            temperature=61,
            telemetry_fresh=True,
            expected_recommendation=FanProfile.AFTERBURNERS,
            expected_simulated=FanProfile.AFTERBURNERS,
            expected_state="simulated",
        ),
        ReplayStep(
            name="afterburners dwell hold",
            advance=10,
            temperature=56,
            telemetry_fresh=True,
            expected_recommendation=FanProfile.AFTERBURNERS,
            expected_simulated=FanProfile.AFTERBURNERS,
            expected_state="aligned",
        ),
        ReplayStep(
            name="afterburners release",
            advance=20,
            temperature=56,
            telemetry_fresh=True,
            expected_recommendation=FanProfile.COOLING_BOOST,
            expected_simulated=FanProfile.COOLING_BOOST,
            expected_state="simulated",
        ),
        ReplayStep(
            name="stale telemetry fallback",
            advance=1,
            temperature=None,
            telemetry_fresh=False,
            expected_recommendation=FanProfile.AUTOMATIC,
            expected_simulated=FanProfile.AUTOMATIC,
            expected_state="simulated",
        ),
    ]

    for step in steps:
        clock.advance(step.advance)

        temperatures = (
            ()
            if step.temperature is None
            else (step.temperature,)
        )

        telemetry["temperatures_c"] = temperatures
        telemetry["telemetry_fresh"] = step.telemetry_fresh

        recommendation = policy.evaluate(
            temperatures,
            telemetry_fresh=step.telemetry_fresh,
        )

        result = coordinator.evaluate(
            recommendation,
            telemetry=telemetry,
            runtime_status=runtime_status,
        )

        assert (
            recommendation.recommended_profile
            is step.expected_recommendation
        ), step.name

        assert (
            coordinator.simulated_profile
            is step.expected_simulated
        ), step.name

        assert result.state == step.expected_state, step.name

    assert service.requests == []


def test_dry_run_stale_telemetry_restores_simulated_automatic():
    """Stale telemetry must abandon a simulated manual profile."""

    clock = FakeClock()
    service = NoHardwareService()

    policy = ThermalFanPolicy(
        balanced_temperature_c=42,
        cooling_boost_temperature_c=50,
        afterburners_temperature_c=60,
        hysteresis_c=3,
        minimum_dwell_seconds=30,
        clock=clock,
    )

    coordinator = ThermalControlCoordinator(
        service,
        policy_mode="automatic_control",
        operator_armed=True,
        dry_run=True,
        command_cooldown_seconds=30,
        clock=clock,
    )

    runtime_status = {
        "connected": True,
        "active_profile": "automatic",
        "safety_hold": False,
        "recovery_pending": False,
    }

    telemetry = {
        "fan_status": {
            "fan_channels": [
                {
                    "number": 1,
                    "rpm": 1800,
                    "alarm": False,
                },
                {
                    "number": 2,
                    "rpm": 1800,
                    "alarm": False,
                },
            ]
        },
        "temperatures_c": (61,),
        "telemetry_fresh": True,
    }

    hot = policy.evaluate(
        telemetry["temperatures_c"],
        telemetry_fresh=True,
    )

    coordinator.evaluate(
        hot,
        telemetry=telemetry,
        runtime_status=runtime_status,
    )

    assert (
        coordinator.simulated_profile
        is FanProfile.AFTERBURNERS
    )

    telemetry["temperatures_c"] = ()
    telemetry["telemetry_fresh"] = False

    stale = policy.evaluate(
        (),
        telemetry_fresh=False,
    )

    result = coordinator.evaluate(
        stale,
        telemetry=telemetry,
        runtime_status=runtime_status,
    )

    assert (
        coordinator.simulated_profile
        is FanProfile.AUTOMATIC
    )
    assert result.state == "simulated"
    assert service.requests == []
