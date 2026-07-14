from truepanel.lab.widgets.render import (
    LCD_WIDTH,
    WidgetRenderer,
)


def test_cpu_bar_is_ascii_safe():
    renderer = WidgetRenderer()

    assert renderer.cpu(50) == "####----"


def test_ram_bar_is_ascii_safe():
    renderer = WidgetRenderer()

    assert renderer.ram(75) == "######--"


def test_performance_lines():
    renderer = WidgetRenderer()

    line1, line2 = renderer.performance_lines(
        50,
        75,
    )

    assert line1 == "CPU ####--- 50% "
    assert line2 == "RAM #####-- 75% "


def test_performance_lines_are_lcd_width():
    renderer = WidgetRenderer()

    lines = renderer.performance_lines(
        100,
        100,
    )

    assert all(
        len(line) == LCD_WIDTH
        for line in lines
    )


def test_performance_values_are_clamped():
    renderer = WidgetRenderer()

    line1, line2 = renderer.performance_lines(
        -20,
        500,
    )

    assert line1 == "CPU ------- 0%  "
    assert line2 == "RAM ####### 100%"


def test_performance_values_are_rounded():
    renderer = WidgetRenderer()

    line1, line2 = renderer.performance_lines(
        49.6,
        24.5,
    )

    assert line1.endswith("50% ")
    assert line2.endswith("24% ")
