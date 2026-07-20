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


def discover_fan_channels(base):
    """
    Return every fan tachometer channel exposed by the controller.

    A zero-RPM channel is reported exactly as the kernel exposes it. TruePanel
    does not assume that the channel represents a failed fan because it may be
    an unpopulated motherboard header.
    """
    channels = []

    if base is None:
        return channels

    for input_path in sorted(
        Path(base).glob("fan*_input")
    ):
        name = input_path.name
        number_text = name[
            len("fan"):-len("_input")
        ]

        try:
            number = int(number_text)
        except ValueError:
            continue

        alarm_value = read_int(
            Path(base)
            / f"fan{number}_alarm",
            None,
        )

        channels.append(
            {
                "number": number,
                "rpm": read_int(
                    input_path,
                    0,
                ),
                "alarm": (
                    bool(alarm_value)
                    if alarm_value is not None
                    else None
                ),
                "pwm": read_int(
                    Path(base)
                    / f"pwm{number}",
                    None,
                ),
                "pwm_mode": pwm_mode(
                    read_int(
                        Path(base)
                        / f"pwm{number}_enable",
                        None,
                    )
                ),
            }
        )

    return channels


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
            "fan_channels": [],
        }

    channels = discover_fan_channels(
        base
    )
    channels_by_number = {
        channel["number"]: channel
        for channel in channels
    }

    fan1 = channels_by_number.get(
        1,
        {},
    )
    fan2 = channels_by_number.get(
        2,
        {},
    )

    return {
        "base": str(base),
        "available": True,
        "fan1_rpm": fan1.get(
            "rpm",
            0,
        ),
        "fan2_rpm": fan2.get(
            "rpm",
            0,
        ),
        "pwm1": fan1.get(
            "pwm",
            0,
        )
        or 0,
        "pwm2": fan2.get(
            "pwm",
            0,
        )
        or 0,
        "pwm1_mode": fan1.get(
            "pwm_mode",
            "Unavailable",
        ),
        "pwm2_mode": fan2.get(
            "pwm_mode",
            "Unavailable",
        ),
        "fan_channels": channels,
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
