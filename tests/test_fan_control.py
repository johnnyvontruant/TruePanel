from truepanel.hardware.fan_control import (
    FanControlInterlock,
)




def test_custom_profile_pwm_is_used():
    interlock = FanControlInterlock(
        profile_pwm={
            "quiet": 180,
            "balanced": 205,
            "cooling_boost": 235,
            "afterburners": 200,
        }
    )

    decision = interlock.evaluate(
        "balanced",
        fan_status={
            "fan_channels": [
                {
                    "number": 1,
                    "rpm": 1500,
                    "alarm": False,
                },
                {
                    "number": 2,
                    "rpm": 1500,
                    "alarm": False,
                },
            ]
        },
        temperatures_c=(45,),
    )

    assert decision.pwm == 205


def test_afterburners_pwm_cannot_be_reduced():
    interlock = FanControlInterlock(
        profile_pwm={
            "afterburners": 180,
        }
    )

    decision = interlock.evaluate(
        "afterburners",
        fan_status={},
        temperatures_c=(),
        telemetry_fresh=False,
    )

    assert decision.pwm == 255
