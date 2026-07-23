from pathlib import Path


def test_lcd_runtime_builds_fan_control_runtime():
    source = Path(
        "lcd-menu.py"
    ).read_text()

    assert (
        "build_fan_control_runtime"
        in source
    )

    assert (
        "fan_control_runtime = "
        "build_fan_control_runtime("
        in source
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
        "def build_fan_command_server():",
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
