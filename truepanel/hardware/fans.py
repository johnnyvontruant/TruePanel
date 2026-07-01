from pathlib import Path
from truepanel.hardware.discovery import find_fintek_hwmon

BASE = find_fintek_hwmon()

if BASE is None:
    BASE = Path("/sys/class/hwmon/hwmon10/device")


def path(name):
    return BASE / name


def read_int(file_path, default=0):
    try:
        return int(Path(file_path).read_text().strip())
    except Exception:
        return default


def write_int(file_path, value):
    Path(file_path).write_text(str(int(value)))


def pwm_mode(value):
    if value == 1:
        return "Manual"
    if value == 2:
        return "Auto"
    return f"Mode {value}"


def get_status():
    pwm1_enable = read_int(path("pwm1_enable"), None)
    pwm2_enable = read_int(path("pwm2_enable"), None)

    return {
        "base": str(BASE),
        "fan1_rpm": read_int(path("fan1_input")),
        "fan2_rpm": read_int(path("fan2_input")),
        "pwm1": read_int(path("pwm1")),
        "pwm2": read_int(path("pwm2")),
        "pwm1_mode": pwm_mode(pwm1_enable),
        "pwm2_mode": pwm_mode(pwm2_enable),
    }


def set_auto():
    write_int(path("pwm1_enable"), 2)
    write_int(path("pwm2_enable"), 2)


def set_manual_pwm(value):
    value = max(0, min(255, int(value)))
    write_int(path("pwm1_enable"), 1)
    write_int(path("pwm2_enable"), 1)
    write_int(path("pwm1"), value)
    write_int(path("pwm2"), value)

PROFILES = {
    "Auto": None,
    "Quiet": 150,
    "Balanced": 185,
    "Performance": 220,
    "Full": 255,
}


def apply_profile(name):
    if name == "Auto":
        set_auto()
        return

    value = PROFILES.get(name)
    if value is None:
        raise ValueError(f"Unknown fan profile: {name}")

    set_manual_pwm(value)
