from pathlib import Path


def source():
    return Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )


def test_lcd_runtime_imports_host_agent_runtime():
    text = source()

    assert (
        "from truepanel.host import HostAgentRuntime"
        in text
    )


def test_lcd_constructs_host_agent_runtime():
    text = source()

    assert (
        "host_agent_runtime = HostAgentRuntime("
        in text
    )

    assert (
        "fan_runtime=fan_control_runtime"
        in text
    )

    assert (
        "fan_server_factory=("
        in text
    )

    assert (
        "build_fan_command_server"
        in text
    )

    assert (
        "lcd_server_factory=("
        in text
    )

    assert (
        "build_lcd_command_server"
        in text
    )


def test_host_agent_starts_before_visual_startup():
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


def test_status_publishes_before_host_agent_start():
    text = source()

    status_publish = text.index(
        "publish_fan_control_status()",
        text.index("def main():"),
    )

    host_start = text.index(
        "host_agent_runtime.start()"
    )

    assert status_publish < host_start


def test_host_agent_owns_shutdown():
    text = source()

    assert (
        "host_agent_runtime.shutdown()"
        in text
    )


def test_fallback_shutdown_restores_fan_runtime():
    text = source()

    shutdown_start = text.index(
        "finally:",
        text.index("def main():"),
    )

    shutdown = text[
        shutdown_start:
    ]

    assert (
        "fan_control_runtime.shutdown()"
        in shutdown
    )
