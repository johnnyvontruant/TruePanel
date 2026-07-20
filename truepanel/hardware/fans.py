from pathlib import Path

from truepanel.hardware.discovery import find_fintek_hwmon


def controller_base():
    return find_fintek_hwmon()


def read_int(file_path, default=0):
    if file_path is None:
        return default

    try:
        return int(Path(file_path).read_text().strip())
    except Exception:
        return default


def require_controller():
    base = controller_base()

    if base is None:
        raise RuntimeError(
            "Fintek fan controller is unavailable"
        )

    return base


def pwm_mode(value):
    if value == 1:
        return "Manual"

    if value == 2:
        return "Auto"

    if value is None:
        return "Unavailable"

    return f"Mode {value}"


def get_status():
    base = controller_base()

    if base is None:
        return {
            "base": None,
            "available": False,
            "fan1_rpm": 0,
            "fan2_rpm": 0,
            "pwm1": 0,
            "pwm2": 0,
            "pwm1_mode": "Unavailable",
            "pwm2_mode": "Unavailable",
        }

    pwm1_enable = read_int(
        base / "pwm1_enable",
        None,
    )

    pwm2_enable = read_int(
        base / "pwm2_enable",
        None,
    )

    return {
        "base": str(base),
        "available": True,
        "fan1_rpm": read_int(
            base / "fan1_input"
        ),
        "fan2_rpm": read_int(
            base / "fan2_input"
        ),
        "pwm1": read_int(
            base / "pwm1"
        ),
        "pwm2": read_int(
            base / "pwm2"
        ),
        "pwm1_mode": pwm_mode(
            pwm1_enable
        ),
        "pwm2_mode": pwm_mode(
            pwm2_enable
        ),
    }


def write_int(file_path, value):
    Path(file_path).write_text(
        str(int(value))
    )


def set_auto():
    base = require_controller()

    write_int(
        base / "pwm1_enable",
        2,
    )

    write_int(
        base / "pwm2_enable",
        2,
    )


def set_manual_pwm(value):
    base = require_controller()
    value = max(
        0,
        min(255, int(value)),
    )

    write_int(
        base / "pwm1_enable",
        1,
    )

    write_int(
        base / "pwm2_enable",
        1,
    )

    write_int(
        base / "pwm1",
        value,
    )

    write_int(
        base / "pwm2",
        value,
    )


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
        raise ValueError(
            f"Unknown fan profile: {name}"
        )

    set_manual_pwm(value)
