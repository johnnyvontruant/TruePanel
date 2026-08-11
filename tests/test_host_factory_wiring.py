from pathlib import Path


def source():
    return Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )


def test_lcd_runtime_declares_process_boundary():
    text = source()

    assert "HostAgentSafetyServices" in text
    assert "HostAgentApplicationHooks" in text


def test_safety_services_hold_hardware_policy_hooks():
    text = source()

    start = text.index(
        "host_agent_safety_services = "
        "HostAgentSafetyServices("
    )

    end = text.index(
        "host_agent_application_hooks = ",
        start,
    )

    block = text[start:end]

    assert "fan_telemetry_provider" in block
    assert "fan_status_publisher" in block
    assert "fan_event_recorder" in block
    assert "thermal_control_handler" in block

    assert "lcd_button_handler" not in block


def test_application_hooks_hold_only_lcd_dispatch():
    text = source()

    start = text.index(
        "host_agent_application_hooks = "
        "HostAgentApplicationHooks("
    )

    end = text.index(
        "host_agent_runtime = "
        "build_host_agent_runtime(",
        start,
    )

    block = text[start:end]

    assert "lcd_button_handler" in block
    assert "lcd.submit_button_event(" in block

    assert "thermal_control_handler" not in block
    assert "fan_event_recorder" not in block


def test_factory_receives_explicit_boundaries():
    text = source()

    assert (
        "safety_services=("
        in text
    )

    assert (
        "host_agent_safety_services"
        in text
    )

    assert (
        "application_hooks=("
        in text
    )

    assert (
        "host_agent_application_hooks"
        in text
    )


def test_lcd_runtime_has_no_command_implementation_classes():
    text = source()

    for name in (
        "FanCommandProcessor",
        "FanCommandServer",
        "LCDCommandProcessor",
        "LCDCommandServer",
    ):
        assert name not in text


def test_host_runtime_starts_before_visual_startup():
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
