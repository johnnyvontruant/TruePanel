import math

import pytest

from truepanel.hardware.fan_control import (
    FanProfile,
)
from truepanel.hardware.thermal_fan_policy import (
    ThermalFanPolicy,
)


@pytest.mark.parametrize(
    ("temperature", "expected"),
    (
        (35, FanProfile.QUIET),
        (41.9, FanProfile.QUIET),
        (42, FanProfile.BALANCED),
        (49.9, FanProfile.BALANCED),
        (50, FanProfile.COOLING_BOOST),
        (59.9, FanProfile.COOLING_BOOST),
        (60, FanProfile.AFTERBURNERS),
        (76, FanProfile.AFTERBURNERS),
    ),
)
def test_temperature_bands(
    temperature,
    expected,
):
    policy = ThermalFanPolicy()

    result = policy.evaluate(
        (temperature,)
    )

    assert result.recommended_profile is expected
    assert result.hottest_temperature_c == temperature
    assert result.telemetry_valid is True


def test_hottest_temperature_wins():
    policy = ThermalFanPolicy()

    result = policy.evaluate(
        (38, 47, 55, 41)
    )

    assert (
        result.recommended_profile
        is FanProfile.COOLING_BOOST
    )
    assert result.hottest_temperature_c == 55


def test_upshift_happens_immediately():
    policy = ThermalFanPolicy(
        initial_profile=FanProfile.QUIET
    )

    result = policy.evaluate(
        (60,)
    )

    assert (
        result.recommended_profile
        is FanProfile.AFTERBURNERS
    )
    assert result.changed is True


def test_balanced_holds_until_hysteresis_clears():
    policy = ThermalFanPolicy(
        minimum_dwell_seconds=0,
    )

    assert (
        policy.evaluate((43,))
        .recommended_profile
        is FanProfile.BALANCED
    )

    held = policy.evaluate(
        (40,)
    )

    assert (
        held.recommended_profile
        is FanProfile.BALANCED
    )
    assert "hysteresis" in held.reason

    released = policy.evaluate(
        (38.9,)
    )

    assert (
        released.recommended_profile
        is FanProfile.QUIET
    )


def test_cooling_boost_holds_until_hysteresis_clears():
    policy = ThermalFanPolicy(
        minimum_dwell_seconds=0,
    )

    assert (
        policy.evaluate((52,))
        .recommended_profile
        is FanProfile.COOLING_BOOST
    )

    assert (
        policy.evaluate((48,))
        .recommended_profile
        is FanProfile.COOLING_BOOST
    )

    assert (
        policy.evaluate((46.9,))
        .recommended_profile
        is FanProfile.BALANCED
    )


def test_afterburners_holds_until_hysteresis_clears():
    policy = ThermalFanPolicy(
        minimum_dwell_seconds=0,
    )

    assert (
        policy.evaluate((62,))
        .recommended_profile
        is FanProfile.AFTERBURNERS
    )

    assert (
        policy.evaluate((58,))
        .recommended_profile
        is FanProfile.AFTERBURNERS
    )

    assert (
        policy.evaluate((56.9,))
        .recommended_profile
        is FanProfile.COOLING_BOOST
    )


def test_stale_telemetry_recommends_automatic():
    policy = ThermalFanPolicy(
        initial_profile=FanProfile.COOLING_BOOST
    )

    result = policy.evaluate(
        (55,),
        telemetry_fresh=False,
    )

    assert (
        result.recommended_profile
        is FanProfile.AUTOMATIC
    )
    assert result.telemetry_valid is False
    assert result.changed is True


def test_missing_telemetry_recommends_automatic():
    policy = ThermalFanPolicy()

    result = policy.evaluate(())

    assert (
        result.recommended_profile
        is FanProfile.AUTOMATIC
    )
    assert result.telemetry_valid is False


def test_invalid_values_are_ignored():
    policy = ThermalFanPolicy()

    result = policy.evaluate(
        (
            None,
            "invalid",
            math.nan,
            math.inf,
            -100,
            200,
            48,
        )
    )

    assert (
        result.recommended_profile
        is FanProfile.BALANCED
    )
    assert result.hottest_temperature_c == 48


def test_all_invalid_values_recommend_automatic():
    policy = ThermalFanPolicy()

    result = policy.evaluate(
        (
            None,
            math.nan,
            math.inf,
            -100,
            200,
        )
    )

    assert (
        result.recommended_profile
        is FanProfile.AUTOMATIC
    )
    assert result.telemetry_valid is False


def test_thresholds_must_increase():
    with pytest.raises(
        ValueError,
        match="thresholds must increase",
    ):
        ThermalFanPolicy(
            balanced_temperature_c=50,
            cooling_boost_temperature_c=45,
            afterburners_temperature_c=60,
        )


def test_hysteresis_cannot_be_negative():
    with pytest.raises(
        ValueError,
        match="cannot be negative",
    ):
        ThermalFanPolicy(
            hysteresis_c=-1
        )


def test_module_is_observe_only():
    source = (
        __import__(
            "pathlib"
        )
        .Path(
            "truepanel/hardware/"
            "thermal_fan_policy.py"
        )
        .read_text(
            encoding="utf-8"
        )
    )

    assert "write_int" not in source
    assert "set_manual_pwm" not in source
    assert "FanHardwareExecutor" not in source
    assert "/sys/" not in source


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def test_downshift_waits_for_minimum_dwell():
    clock = FakeClock()
    policy = ThermalFanPolicy(
        minimum_dwell_seconds=30,
        clock=clock,
    )

    assert (
        policy.evaluate((52,))
        .recommended_profile
        is FanProfile.COOLING_BOOST
    )

    clock.advance(10)

    held = policy.evaluate((45,))

    assert (
        held.recommended_profile
        is FanProfile.COOLING_BOOST
    )
    assert "minimum dwell" in held.reason

    clock.advance(20)

    released = policy.evaluate((45,))

    assert (
        released.recommended_profile
        is FanProfile.BALANCED
    )


def test_upshift_ignores_dwell_timer():
    clock = FakeClock()
    policy = ThermalFanPolicy(
        minimum_dwell_seconds=300,
        initial_profile=FanProfile.QUIET,
        clock=clock,
    )

    clock.advance(1)

    result = policy.evaluate((61,))

    assert (
        result.recommended_profile
        is FanProfile.AFTERBURNERS
    )


def test_negative_dwell_is_rejected():
    with pytest.raises(
        ValueError,
        match="dwell time cannot be negative",
    ):
        ThermalFanPolicy(
            minimum_dwell_seconds=-1
        )
