import subprocess
import sys
from pathlib import Path


DRILL = Path(
    "development/fan_safety_drill.py"
)


def test_fan_safety_drill_passes():
    result = subprocess.run(
        [
            sys.executable,
            str(DRILL),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        result.stdout
        + result.stderr
    )
    assert (
        "Fan Control Phase 6: PASS"
        in result.stdout
    )
    assert (
        "Hardware access: DISABLED"
        in result.stdout
    )
    assert (
        "RECORDER Safety recovery once"
        in result.stdout
    )
    assert (
        "PWM      Exactly two applications"
        in result.stdout
    )


def test_drill_has_no_direct_hardware_imports():
    source = DRILL.read_text(
        encoding="utf-8"
    )

    forbidden = [
        "FanControlExecutor",
        "Fintek",
        "get_fan_status",
        "truepanel.hardware.fans",
        "/sys/class/hwmon",
        "/dev/",
        "FanCommandServer",
    ]

    for token in forbidden:
        assert token not in source
