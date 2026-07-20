from pathlib import Path
import ast


def source_text():
    return Path("lcd-menu.py").read_text(
        encoding="utf-8",
    )


def test_page_counter_is_installed():
    source = source_text()

    assert "def page_counter():" in source
    assert "def add_page_counter(lines):" in source
    assert "def render_menu_page():" in source


def test_page_counter_uses_live_menu_length():
    source = source_text()

    assert "total = max(1, len(menu))" in source
    assert "(menu_item % total) + 1" in source


def test_page_counter_reserves_right_side_of_first_row():
    source = source_text()

    assert "16 - len(counter)" in source
    assert "first[:title_width].ljust(title_width)" in source


def test_automatic_rotation_uses_counted_renderer():
    source = source_text()

    loop_start = source.index(
        "        while not shutdown_requested:"
    )

    loop_end = source.index(
        "    finally:",
        loop_start,
    )

    loop_source = source[
        loop_start:loop_end
    ]

    assert "render_menu_page()" in loop_source
    assert "menu_item + 1" in loop_source


def test_button_navigation_uses_counted_renderer():
    source = source_text()

    handler_start = source.index(
        "def response_handler"
    )

    handler_end = source.index(
        "def main",
        handler_start,
    )

    handler_source = source[
        handler_start:handler_end
    ]

    assert (
        "if prev_menu != menu_item:"
        in handler_source
    )

    assert (
        "render_menu_page()"
        in handler_source
    )


def test_rotation_is_five_seconds():
    source = source_text()

    assert "            delay = 5" in source


def test_backlight_timeout_is_two_minutes():
    source = source_text()

    assert "DISPLAY_TIMEOUT = 120" in source


def test_lcd_menu_remains_valid_python():
    source = source_text()
    ast.parse(source)
