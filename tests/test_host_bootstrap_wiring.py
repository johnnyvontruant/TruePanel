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




def test_host_bootstrap_owns_history_behavior():
    runtime = source()

    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "host_bootstrap.record_fan_event("
        in runtime
    )

    assert (
        "host_bootstrap.record_commissioning_event("
        in runtime
    )

    assert (
        "host_bootstrap.fan_event_source("
        in runtime
    )

    assert (
        "fan_control_history.append("
        not in runtime
    )

    assert (
        "thermal_commissioning_history.append("
        not in runtime
    )

    assert "event_from_decision(" in bootstrap
    assert "commissioning_event(" in bootstrap

    assert (
        "fan_control_history.append("
        in bootstrap
    )

    assert (
        "thermal_commissioning_history.append("
        in bootstrap
    )

def test_automatic_restoration_has_no_lcd_hardware_fallback():
    runtime = source()

    start = runtime.index(
        "def restore_motherboard_fan_control("
    )

    end = runtime.index(
        "\ndef ",
        start + 1,
    )

    block = runtime[start:end]

    assert (
        ".safety"
        in block
    )

    assert (
        ".restore_automatic("
        in block
    )

    assert (
        ".request_profile("
        not in block
    )
