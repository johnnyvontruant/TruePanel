from pathlib import Path

from truepanel.hardware.lcd_service import (
    build_lcd_command_server,
)


def test_lcd_service_builder_owns_virtual_button_server():
    calls = []

    def submit(mask, source):
        calls.append((mask, source))
        return True

    server = build_lcd_command_server(
        submit_button=submit
    )

    assert server is not None
    assert server.processor.submit_button is submit


def test_lcd_service_builder_fails_closed_without_handler():
    assert build_lcd_command_server(
        submit_button=None
    ) is None


def test_lcd_runtime_owns_lcd_command_server_lifecycle():
    source = Path(
        "lcd-menu.py"
    ).read_text(encoding="utf-8")
    host_runtime = Path(
        "truepanel/host/runtime.py"
    ).read_text(encoding="utf-8")
    host_factory = Path(
        "truepanel/host/factory.py"
    ).read_text(encoding="utf-8")

    assert "build_lcd_command_server" in source
    assert "lcd_command_server.start()" in source
    assert "lcd_command_server.stop()" in source
    assert "lcd.submit_button_event(" in source

    assert "lcd_server_factory" not in host_runtime
    assert "_lcd_server" not in host_runtime
    assert "LCDCommandServer" not in host_factory
    assert "LCDCommandProcessor" not in host_factory


def test_lcd_command_server_stops_before_host_hardware_shutdown():
    source = Path(
        "lcd-menu.py"
    ).read_text(encoding="utf-8")
    finally_start = source.index("    finally:")
    block = source[finally_start:]

    lcd_stop = block.index("lcd_command_server.stop()")
    host_stop = block.index("host_agent_runtime.shutdown()")

    assert lcd_stop < host_stop


def test_standalone_host_has_no_lcd_command_application_hook():
    agent = Path(
        "truepanel/host/agent.py"
    ).read_text(encoding="utf-8")

    assert "HostAgentApplicationHooks" not in agent
    assert "lcd_button_handler" not in agent
