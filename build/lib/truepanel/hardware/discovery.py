from pathlib import Path


def find_fintek_hwmon():
    """
    Find the Fintek fan controller hwmon device.

    On the TVS-671 this appears as something like:
    /sys/class/hwmon/hwmon10/device
    with a device name of f71869a / f71882fg.
    """
    for hwmon in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
        device = hwmon / "device"
        name_file = device / "name"

        try:
            name = name_file.read_text().strip().lower()
        except Exception:
            continue

        if name.startswith("f718") or "fintek" in name:
            return device

        if all((device / f).exists() for f in ["fan1_input", "pwm1", "pwm1_enable"]):
            return device

    return None
