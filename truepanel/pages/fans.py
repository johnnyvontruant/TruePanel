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
