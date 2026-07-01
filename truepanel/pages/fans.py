from truepanel.hardware.fans import get_status


def fan_rpm_page():
    status = get_status()
    return [
        f'Fan1 {status["fan1_rpm"]:>5}RPM',
        f'Fan2 {status["fan2_rpm"]:>5}RPM',
    ]


def fan_pwm_page():
    status = get_status()
    return [
        f'PWM1 {status["pwm1"]:>3} {status["pwm1_mode"][:4]}',
        f'PWM2 {status["pwm2"]:>3} {status["pwm2_mode"][:4]}',
    ]
