from pathlib import Path

BASE = Path("/sys/class/hwmon/hwmon10/device")

FAN1 = BASE / "fan1_input"
FAN2 = BASE / "fan2_input"
PWM1 = BASE / "pwm1"
PWM2 = BASE / "pwm2"
PWM1_ENABLE = BASE / "pwm1_enable"
PWM2_ENABLE = BASE / "pwm2_enable"


def read_int(path, default=None):
    try:
        return int(Path(path).read_text().strip())
    except Exception:
        return default


def pwm_mode(value):
    if value == 1:
        return "Manual"
    if value == 2:
        return "Auto"
    return f"Mode {value}" if value is not None else "Unknown"


def get_fan_status():
    return {
        "fan1_rpm": read_int(FAN1, 0),
        "fan2_rpm": read_int(FAN2, 0),
        "pwm1": read_int(PWM1, 0),
        "pwm2": read_int(PWM2, 0),
        "pwm1_mode": pwm_mode(read_int(PWM1_ENABLE)),
        "pwm2_mode": pwm_mode(read_int(PWM2_ENABLE)),
    }


def get_lcd_pages():
    status = get_fan_status()

    page1 = [
        f"Fan1 {status['fan1_rpm']:>5}RPM",
        f"Fan2 {status['fan2_rpm']:>5}RPM",
    ]

    page2 = [
        f"PWM1 {status['pwm1']:>3} {status['pwm1_mode'][:4]}",
        f"PWM2 {status['pwm2']:>3} {status['pwm2_mode'][:4]}",
    ]

    return [page1, page2]


if __name__ == "__main__":
    status = get_fan_status()
    print(status)
    for page in get_lcd_pages():
        print(page)
