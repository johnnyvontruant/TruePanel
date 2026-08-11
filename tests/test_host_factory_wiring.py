from pathlib import Path


def source():
    return Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )


def test_lcd_runtime_uses_host_agent_factory():
    text = source()

    assert (
        "from truepanel.host import build_host_agent_runtime"
        in text
    )

    assert (
        "host_agent_runtime = build_host_agent_runtime("
        in text
    )


def test_lcd_runtime_no_longer_builds_command_servers():
    text = source()

    assert (
        "def build_fan_command_server():"
        not in text
    )

    assert (
        "def build_lcd_command_server():"
        not in text
    )

    assert (
        "FanCommandProcessor"
        not in text
    )

    assert (
        "FanCommandServer"
        not in text
    )

    assert (
        "LCDCommandProcessor"
        not in text
    )

    assert (
        "LCDCommandServer"
        not in text
    )


def test_factory_receives_fan_runtime_hooks():
    text = source()

    assert (
        "fan_runtime=fan_control_runtime"
        in text
    )

    assert (
        "fan_telemetry_provider=("
        in text
    )

    assert (
        "fan_command_telemetry"
        in text
    )

    assert (
        "fan_status_publisher=("
        in text
    )

    assert (
        "publish_fan_control_status"
        in text
    )

    assert (
        "thermal_control_handler=("
        in text
    )

    assert (
        "set_thermal_operator_arm_state"
        in text
    )


def test_factory_receives_lcd_button_hook():
    text = source()

    assert (
        "lcd_button_handler=("
        in text
    )

    assert (
        "lcd.submit_button_event("
        in text
    )


def test_host_runtime_still_starts_before_visual_startup():
    text = source()

    main_start = text.index(
        "def main():"
    )

    host_start = text.index(
        "host_agent_runtime.start()",
        main_start,
    )

    animation_start = text.index(
        "bay_led_startup_animation.run()",
        main_start,
    )

    splash_start = text.index(
        "show_startup_splash()",
        main_start,
    )

    buzzer_start = text.index(
        "buzzer.startup()",
        main_start,
    )

    assert host_start < animation_start
    assert host_start < splash_start
    assert host_start < buzzer_start


def test_host_runtime_still_owns_shutdown():
    text = source()

    assert (
        "host_agent_runtime.shutdown()"
        in text
    )
