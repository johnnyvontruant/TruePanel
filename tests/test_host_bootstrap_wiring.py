from pathlib import Path


def source():
    return Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )


def test_lcd_runtime_uses_host_bootstrap():
    text = source()

    assert (
        "host_bootstrap = "
        "build_host_agent_bootstrap("
        in text
    )

    assert (
        "fan_control_runtime = "
        "host_bootstrap.fan_runtime"
        in text
    )

    assert (
        "host_bootstrap.thermal_authority"
        in text
    )

    assert (
        "host_bootstrap.fan_control_history"
        in text
    )

    assert (
        "host_bootstrap."
        "thermal_commissioning_history"
        in text
    )


def test_lcd_runtime_no_longer_constructs_host_dependencies():
    text = source()

    assert "build_fan_control_runtime(" not in text
    assert "HostThermalAuthority(" not in text

    assert (
        "FanControlHistory("
        not in text
    )

    assert (
        "ThermalCommissioningHistory("
        not in text
    )


def test_observer_history_remains_application_owned():
    text = source()

    assert (
        "thermal_observer_history = "
        "ThermalObserverHistory("
        in text
    )
