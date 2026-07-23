from truepanel.hardware.fans import get_status


LCD_WIDTH = 16


def _rpm_line(number, rpm):
    rpm = max(0, int(rpm or 0))

    return (
        f"Fan {number} {rpm:>5} RPM"
    )[:LCD_WIDTH]


def fan_rpm_page():
    status = get_status()

    if not status.get("available", True):
        return [
            "Fan RPM",
            "Unavailable",
        ]

    return [
        _rpm_line(
            1,
            status.get("fan1_rpm", 0),
        ),
        _rpm_line(
            2,
            status.get("fan2_rpm", 0),
        ),
    ]

def fan_pwm_page():
    status = get_status()

    if not status.get("available", True):
        return [
            "Fan PWM",
            "Unavailable",
        ]

    pwm1 = status.get("pwm1", 0)
    pwm2 = status.get("pwm2", 0)
    mode1 = status.get("pwm1_mode", "")
    mode2 = status.get("pwm2_mode", "")

    return [
        f"PWM1 {pwm1:>3} {mode1[:4]}"[:LCD_WIDTH],
        f"PWM2 {pwm2:>3} {mode2[:4]}"[:LCD_WIDTH],
    ]


def _profile_label(
    profile,
):
    return str(
        profile
        or "automatic"
    ).replace(
        "_",
        " ",
    ).upper()


def fan_control_page(
    status=None,
):
    status = status or {}

    if not status:
        return [
            "FAN CONTROL",
            "STATUS UNKNOWN",
        ]

    if not status.get(
        "enabled",
        False,
    ):
        return [
            "FAN CONTROL",
            "DISABLED",
        ]

    if not status.get(
        "connected",
        False,
    ):
        return [
            "FAN CONTROL",
            "UNAVAILABLE",
        ]

    active = str(
        status.get(
            "active_profile",
            "automatic",
        )
    ).strip().lower()

    safety_hold = bool(
        status.get(
            "safety_hold",
            False,
        )
    )

    recovery_count = max(
        0,
        int(
            status.get(
                "recovery_healthy_cycles",
                0,
            )
            or 0
        ),
    )
    recovery_required = max(
        1,
        int(
            status.get(
                "recovery_required_cycles",
                3,
            )
            or 3
        ),
    )

    if safety_hold:
        if recovery_count > 0:
            return [
                "FAN RECOVERY",
                (
                    f"{recovery_count} / "
                    f"{recovery_required} HEALTHY"
                )[:LCD_WIDTH],
            ]

        return [
            "FAN SAFETY",
            "HOLD ACTIVE",
        ]

    remaining = status.get(
        "remaining_seconds"
    )

    if (
        active != "automatic"
        and remaining is not None
    ):
        try:
            seconds = max(
                0,
                int(
                    float(remaining)
                ),
            )
        except (
            TypeError,
            ValueError,
        ):
            seconds = 0

        return [
            "FAN MANUAL",
            (
                f"{_profile_label(active)} "
                f"{seconds}s"
            )[:LCD_WIDTH],
        ]

    return [
        "FAN CONTROL",
        _profile_label(
            active
        )[:LCD_WIDTH],
    ]
