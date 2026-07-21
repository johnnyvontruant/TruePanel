import pytest

from truepanel.hardware.fan_control import (
    FanControlInterlock,
    FanProfile,
)


def healthy_status():
    return {
        "fan_channels": [
            {
                "number": 1,
                "rpm": 1577,
                "alarm": False,
            },
            {
                "number": 2,
                "rpm": 1516,
                "alarm": False,
            },
            {
                "number": 3,
                "rpm": 0,
                "alarm": True,
            },
        ]
    }


def test_balanced_profile_is_accepted():
    interlock = FanControlInterlock()

    decision = interlock.evaluate(
        "balanced",
        fan_status=healthy_status(),
        temperatures_c=(51, 41, 47),
    )

    assert decision.accepted
    assert decision.effective_profile is FanProfile.BALANCED
    assert decision.pwm == 194


def test_unused_third_channel_is_ignored():
    interlock = FanControlInterlock(
        controlled_channels=(1, 2)
    )

    decision = interlock.evaluate(
        "quiet",
        fan_status=healthy_status(),
        temperatures_c=(51, 41, 47),
    )

    assert decision.accepted
    assert decision.pwm == 170


def test_stale_telemetry_forces_automatic():
    interlock = FanControlInterlock()

    decision = interlock.evaluate(
        "quiet",
        fan_status=healthy_status(),
        temperatures_c=(51,),
        telemetry_fresh=False,
    )

    assert not decision.accepted
    assert decision.force_automatic
    assert decision.effective_profile is FanProfile.AUTOMATIC


def test_missing_temperature_forces_automatic():
    interlock = FanControlInterlock()

    decision = interlock.evaluate(
        "balanced",
        fan_status=healthy_status(),
        temperatures_c=(),
    )

    assert not decision.accepted
    assert decision.force_automatic


def test_high_temperature_blocks_manual_profile():
    interlock = FanControlInterlock(
        maximum_temperature_c=65,
        emergency_temperature_c=75,
    )

    decision = interlock.evaluate(
        "quiet",
        fan_status=healthy_status(),
        temperatures_c=(68,),
    )

    assert not decision.accepted
    assert decision.force_automatic


def test_emergency_temperature_forces_afterburners():
    interlock = FanControlInterlock(
        maximum_temperature_c=65,
        emergency_temperature_c=75,
    )

    decision = interlock.evaluate(
        "balanced",
        fan_status=healthy_status(),
        temperatures_c=(76,),
    )

    assert decision.accepted
    assert decision.effective_profile is FanProfile.AFTERBURNERS
    assert decision.pwm == 255


def test_failed_controlled_fan_forces_afterburners():
    status = healthy_status()
    status["fan_channels"][0]["rpm"] = 0
    status["fan_channels"][0]["alarm"] = True

    interlock = FanControlInterlock()

    decision = interlock.evaluate(
        "quiet",
        fan_status=status,
        temperatures_c=(51,),
    )

    assert not decision.accepted
    assert decision.effective_profile is FanProfile.AFTERBURNERS
    assert decision.pwm == 255


def test_afterburners_always_available():
    interlock = FanControlInterlock()

    decision = interlock.evaluate(
        "afterburners",
        fan_status={},
        temperatures_c=(),
        telemetry_fresh=False,
    )

    assert decision.accepted
    assert decision.effective_profile is FanProfile.AFTERBURNERS
    assert decision.pwm == 255


def test_automatic_always_available():
    interlock = FanControlInterlock()

    decision = interlock.evaluate(
        "automatic",
        fan_status={},
        temperatures_c=(),
        telemetry_fresh=False,
    )

    assert decision.accepted
    assert decision.force_automatic
    assert decision.pwm is None


def test_unknown_profile_is_rejected():
    interlock = FanControlInterlock()

    with pytest.raises(ValueError):
        interlock.evaluate(
            "warp-eleven",
            fan_status=healthy_status(),
            temperatures_c=(51,),
        )
