from pathlib import Path


def test_lcd_runtime_builds_fan_control_runtime():
    runtime = Path(
        "lcd-menu.py"
    ).read_text()

    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text()

    assert (
        "build_host_agent_bootstrap("
        in runtime
    )

    assert (
        "fan_control_runtime = "
        "host_bootstrap.fan_runtime"
        in runtime
    )

    assert (
        "build_fan_control_runtime"
        in bootstrap
    )


def test_lcd_runtime_publishes_runtime_status():
    source = Path(
        "lcd-menu.py"
    ).read_text()

    assert (
        "fan_control_runtime"
        ".status_payload()"
        in source.replace(
            "\n",
            "",
        ).replace(
            " ",
            "",
        )
    )


def test_lcd_runtime_shuts_down_fan_control():
    source = Path(
        "lcd-menu.py"
    ).read_text()

    assert (
        "fan_control_runtime.shutdown()"
        in source
    )


def test_fan_history_uses_post_transition_telemetry():
    source = Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8",
    )

    assert (
        "post_transition_telemetry = ("
        in source
    )
    assert (
        "fan_command_telemetry(),"
        in source
    )
    assert (
        "decision,\n"
        "            post_transition_telemetry,"
        in source
    )


def test_lcd_classifies_completed_safety_recovery():
    text = Path("lcd-menu.py").read_text()

    assert (
        "def fan_control_event_source("
        in text
    )
    assert (
        '"safety recovery confirmed"'
        in text
    )
    assert (
        'return "recovery"'
        in text
    )


def test_lcd_preserves_timeout_classification():
    text = Path("lcd-menu.py").read_text()

    assert (
        'and "expired" in reason_lower'
        in text
    )
    assert (
        'return "timeout"'
        in text
    )


def test_lcd_records_reconcile_source_from_classifier():
    text = Path("lcd-menu.py").read_text()

    reconcile_start = text.index(
        "def reconcile_fan_control():"
    )
    reconcile_end = text.index(
        "\ndef ",
        reconcile_start,
    )
    reconcile = text[
        reconcile_start:reconcile_end
    ]

    assert (
        "source = fan_control_event_source("
        in reconcile
    )
    assert (
        "record_fan_control_event("
        in reconcile
    )


def test_lcd_wires_fan_control_status_page():
    text = Path("lcd-menu.py").read_text()

    assert "fan_control_page" in text
    assert "def show_fan_control():" in text
    assert (
        "fan_control_status_bridge.read("
        in text
    )


def test_fan_control_page_sits_between_rpm_and_pwm():
    text = Path("lcd-menu.py").read_text()

    menu_start = text.index(
        "menu = ["
    )
    menu_end = text.index(
        "]",
        menu_start,
    )
    menu = text[
        menu_start:menu_end
    ]

    assert (
        menu.index("show_fan_rpm")
        < menu.index("show_fan_control")
        < menu.index("show_fan_pwm")
    )
