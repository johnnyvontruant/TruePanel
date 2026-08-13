from pathlib import Path


def source():
    return Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )


def bootstrap_source():
    return Path(
        "truepanel/host/bootstrap.py"
    ).read_text(
        encoding="utf-8"
    )


def test_lcd_runtime_declares_process_boundary():
    text = source()
    bootstrap = bootstrap_source()

    assert "HostAgentSafetyServices" not in text
    assert "HostAgentSafetyServices" in bootstrap
    assert "HostAgentApplicationHooks" not in text
    assert "build_lcd_command_server" in text


def test_safety_services_hold_hardware_policy_hooks():
    bootstrap = bootstrap_source()

    start = bootstrap.index(
        "    def safety_services("
    )

    end = bootstrap.index(
        "    def record_fan_event(",
        start,
    )

    block = bootstrap[start:end]

    assert "fan_telemetry_provider" in block
    assert "fan_status_publisher" in block
    assert "fan_event_recorder" in block
    assert "thermal_control_handler" in block

    assert "lcd_button_handler" not in block


def test_lcd_application_owns_virtual_button_dispatch():
    text = source()

    start = text.index(
        "lcd_command_server = build_lcd_command_server("
    )
    end = text.index(
        "if bay_led_startup_animation is not None:",
        start,
    )
    block = text[start:end]

    assert "lcd.submit_button_event(" in block
    assert "host_agent_runtime" not in block
    assert "host_bootstrap" not in block


def test_factory_receives_only_privileged_boundaries_from_lcd():
    text = source()
    factory = Path(
        "truepanel/host/factory.py"
    ).read_text(encoding="utf-8")

    assert "safety_services=(" not in text
    assert "host_agent_safety_services" not in text
    assert "application_hooks=(" not in text
    assert "host_agent_application_hooks" not in text
    assert "bootstrap=host_bootstrap" in text
    assert "fan_runtime=bootstrap.fan_runtime" in factory
    assert "safety_services=bootstrap.safety_services()" in factory
    assert "LCDCommandServer" not in factory
    assert "LCDCommandProcessor" not in factory


def test_lcd_runtime_has_no_command_implementation_classes():
    text = source()

    for name in (
        "FanCommandProcessor",
        "FanCommandServer",
        "LCDCommandProcessor",
        "LCDCommandServer",
    ):
        assert name not in text


def test_host_runtime_starts_before_application_command_socket():
    text = source()
    main_start = text.index("def main():")

    host_start = text.index(
        "host_agent_runtime.start()",
        main_start,
    )
    lcd_start = text.index(
        "lcd_command_server.start()",
        main_start,
    )
    animation_start = text.index(
        "bay_led_startup_animation.run()",
        main_start,
    )

    assert host_start < lcd_start < animation_start


def test_application_command_socket_stops_before_host_shutdown():
    text = source()
    finally_start = text.index("    finally:")
    block = text[finally_start:]

    lcd_stop = block.index("lcd_command_server.stop()")
    host_stop = block.index("host_agent_runtime.shutdown()")

    assert lcd_stop < host_stop
