from truepanel.pages import fans


def test_fan_rpm_page_formats_both_fans(
    monkeypatch,
):
    monkeypatch.setattr(
        fans,
        "get_status",
        lambda: {
            "available": True,
            "fan1_rpm": 1438,
            "fan2_rpm": 1408,
        },
    )

    assert fans.fan_rpm_page() == [
        "Fan 1  1438 RPM",
        "Fan 2  1408 RPM",
    ]


def test_fan_rpm_page_fits_lcd(
    monkeypatch,
):
    monkeypatch.setattr(
        fans,
        "get_status",
        lambda: {
            "available": True,
            "fan1_rpm": 123456,
            "fan2_rpm": 987654,
        },
    )

    lines = fans.fan_rpm_page()

    assert len(lines) == 2
    assert all(
        len(line) <= 16
        for line in lines
    )


def test_fan_rpm_page_handles_missing_controller(
    monkeypatch,
):
    monkeypatch.setattr(
        fans,
        "get_status",
        lambda: {
            "available": False,
            "fan1_rpm": 0,
            "fan2_rpm": 0,
        },
    )

    assert fans.fan_rpm_page() == [
        "Fan RPM",
        "Unavailable",
    ]


def test_pwm_page_remains_read_only_display(
    monkeypatch,
):
    monkeypatch.setattr(
        fans,
        "get_status",
        lambda: {
            "available": True,
            "pwm1": 174,
            "pwm2": 174,
            "pwm1_mode": "Auto",
            "pwm2_mode": "Auto",
        },
    )

    assert fans.fan_pwm_page() == [
        "PWM1 174 Auto",
        "PWM2 174 Auto",
    ]
