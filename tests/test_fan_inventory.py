from pathlib import Path

from truepanel.hardware import fans


def write_value(
    base,
    name,
    value,
):
    Path(base, name).write_text(
        str(value)
    )


def test_discover_fan_channels(
    tmp_path,
):
    write_value(
        tmp_path,
        "fan1_input",
        1480,
    )
    write_value(
        tmp_path,
        "fan1_alarm",
        0,
    )
    write_value(
        tmp_path,
        "pwm1",
        182,
    )
    write_value(
        tmp_path,
        "pwm1_enable",
        2,
    )

    write_value(
        tmp_path,
        "fan2_input",
        1463,
    )
    write_value(
        tmp_path,
        "fan2_alarm",
        0,
    )
    write_value(
        tmp_path,
        "pwm2",
        182,
    )
    write_value(
        tmp_path,
        "pwm2_enable",
        2,
    )

    write_value(
        tmp_path,
        "fan3_input",
        0,
    )
    write_value(
        tmp_path,
        "fan3_alarm",
        1,
    )
    write_value(
        tmp_path,
        "pwm3",
        178,
    )
    write_value(
        tmp_path,
        "pwm3_enable",
        2,
    )

    assert (
        fans.discover_fan_channels(
            tmp_path
        )
        == [
            {
                "number": 1,
                "rpm": 1480,
                "alarm": False,
                "pwm": 182,
                "pwm_mode": "Auto",
            },
            {
                "number": 2,
                "rpm": 1463,
                "alarm": False,
                "pwm": 182,
                "pwm_mode": "Auto",
            },
            {
                "number": 3,
                "rpm": 0,
                "alarm": True,
                "pwm": 178,
                "pwm_mode": "Auto",
            },
        ]
    )


def test_get_status_preserves_legacy_keys(
    monkeypatch,
    tmp_path,
):
    write_value(
        tmp_path,
        "fan1_input",
        1500,
    )
    write_value(
        tmp_path,
        "fan2_input",
        1450,
    )
    write_value(
        tmp_path,
        "fan3_input",
        0,
    )

    write_value(
        tmp_path,
        "pwm1",
        182,
    )
    write_value(
        tmp_path,
        "pwm2",
        181,
    )
    write_value(
        tmp_path,
        "pwm3",
        178,
    )

    write_value(
        tmp_path,
        "pwm1_enable",
        2,
    )
    write_value(
        tmp_path,
        "pwm2_enable",
        2,
    )
    write_value(
        tmp_path,
        "pwm3_enable",
        2,
    )

    monkeypatch.setattr(
        fans,
        "controller_base",
        lambda: tmp_path,
    )

    status = fans.get_status()

    assert status["fan1_rpm"] == 1500
    assert status["fan2_rpm"] == 1450
    assert status["pwm1"] == 182
    assert status["pwm2"] == 181
    assert len(
        status["fan_channels"]
    ) == 3
