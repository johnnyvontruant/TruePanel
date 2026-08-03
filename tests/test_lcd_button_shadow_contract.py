from pathlib import Path


LCD_MENU = Path("lcd-menu.py")


def source():
    return LCD_MENU.read_text()


def function_block(text, name, next_name):
    start = text.index(f"def {name}(")
    end = text.index(f"def {next_name}(", start)
    return text[start:end]


def test_shadow_service_uses_reader_owned_button_cache():
    text = source()

    assert (
        "from truepanel.mission_control.button_service import ("
        in text
    )
    assert "ButtonEvent," in text
    assert "ButtonService," in text

    block = function_block(
        text,
        "build_button_shadow_service",
        "response_handler",
    )

    assert "ButtonService(" in block
    assert "active_lcd.read_buttons" in block
    assert "observe_button_event" in block


def test_shadow_event_sink_cannot_navigate():
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

    assert "LOGGER.info" in block
    assert "LOGGER.debug" in block
    assert "ButtonAction.PRESSED" in block
    assert "ButtonAction.RELEASED" in block


def test_legacy_callback_remains_navigation_authority():
    text = source()

    block = function_block(
        text,
        "response_handler",
        "main",
    )

    assert 'if command == "Switch_Status":' in block
    assert "previous_mission_dashboard()" in block
    assert "next_mission_dashboard()" in block
    assert "menu_item = (menu_item - 1)" in block
    assert "menu_item = (menu_item + 1)" in block


def test_shadow_service_has_start_and_stop_lifecycle():
    text = source()

    main_start = text.index("def main():")
    main_block = text[main_start:]

    assert (
        "button_service = build_button_shadow_service("
        in main_block
    )
    assert "button_service.start()" in main_block
    assert "button_service.stop(timeout=2.0)" in main_block

    stop_index = main_block.index(
        "button_service.stop(timeout=2.0)"
    )
    close_index = main_block.index("lcd.close()")

    assert stop_index < close_index
