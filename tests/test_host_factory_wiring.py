from pathlib import Path


def source():
    return Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )


def test_lcd_runtime_uses_host_agent_contract():
    text = source()

    assert (
        "HostAgentApplicationHooks"
        in text
    )

    assert (
        "build_host_agent_runtime"
        in text
    )


def test_lcd_runtime_builds_explicit_hook_surface():
    text = source()

    assert (
        "host_agent_hooks = HostAgentApplicationHooks("
        in text
    )

    assert (
        "fan_telemetry_provider=("
        in text
    )

    assert (
        "fan_status_publisher=("
        in text
    )

    assert (
        "fan_event_recorder="
        in text
    )

    assert (
        "thermal_control_handler=("
        in text
    )

    assert (
        "lcd_button_handler=("
        in text
    )


def test_lcd_runtime_passes_hooks_to_factory():
    text = source()

    assert (
        "host_agent_runtime = build_host_agent_runtime("
        in text
    )

    assert (
        "fan_runtime=fan_control_runtime"
        in text
    )

    assert (
        "hooks=host_agent_hooks"
        in text
    )


def test_lcd_runtime_no_longer_builds_command_servers():
    text = source()

    for name in (
        "FanCommandProcessor",
        "FanCommandServer",
        "LCDCommandProcessor",
        "LCDCommandServer",
    ):
        assert name not in text


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
