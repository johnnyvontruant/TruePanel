from pathlib import Path


LCD_MENU = Path("lcd-menu.py")


def source():
    return LCD_MENU.read_text()


def function_block(text, name, next_name):
    start = text.index(f"def {name}(")
    end = text.index(f"def {next_name}(", start)
    return text[start:end]


def test_shadow_service_consumes_event_queue():
    text = source()

    block = function_block(
        text,
        "build_button_shadow_service",
        "response_handler",
    )

    assert "ButtonService(" in block
    assert "active_lcd.read_button_event" in block
    assert "debounce_samples=1" in block
    assert "repeat_delay=None" in block
    assert "repeat_interval=None" in block


def test_shadow_sink_cannot_navigate():
    text = source()

    block = function_block(
        text,
        "observe_button_event",
        "build_button_shadow_service",
    )

    forbidden = (
        "response_handler(",
        "previous_mission_dashboard(",
        "next_mission_dashboard(",
        "menu_item",
        "lcd_on(",
        "menu[",
        "buzzer.",
    )

    for value in forbidden:
        assert value not in block

    assert "Button queue shadow event:" in block


def test_legacy_callback_remains_authoritative():
    text = source()

    block = function_block(
        text,
        "response_handler",
        "main",
    )

    assert 'if command == "Switch_Status":' in block
    assert "previous_mission_dashboard()" in block
    assert "next_mission_dashboard()" in block


def test_shadow_service_stops_before_lcd_close():
    text = source()
    main_block = text[text.index("def main():"):]

    assert "button_service.start()" in main_block
    assert "button_service.stop(timeout=2.0)" in main_block

    assert (
        main_block.index(
            "button_service.stop(timeout=2.0)"
        )
        < main_block.index("lcd.close()")
    )
