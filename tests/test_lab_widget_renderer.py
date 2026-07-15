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


def test_performance_lines_use_percentages():
    renderer = WidgetRenderer()

    line1, line2 = renderer.performance_lines(
        50,
        75,
    )

    assert line1 == "CPU Usage  50%  "
    assert line2 == "RAM Usage  75%  "


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

    assert line1 == "CPU Usage   0%  "
    assert line2 == "RAM Usage 100%  "


def test_performance_values_are_rounded():
    renderer = WidgetRenderer()

    line1, line2 = renderer.performance_lines(
        49.6,
        24.5,
    )

    assert line1 == "CPU Usage  50%  "
    assert line2 == "RAM Usage  24%  "


def test_invalid_values_default_to_zero():
    renderer = WidgetRenderer()

    line1, line2 = renderer.performance_lines(
        None,
        "not-a-number",
    )

    assert line1 == "CPU Usage   0%  "
    assert line2 == "RAM Usage   0%  "


def test_compact_performance_bars():
    renderer = WidgetRenderer()

    line1, line2 = renderer.performance_bar_lines(
        50,
        75,
    )

    assert line1 == "CPU ###---  50% "
    assert line2 == "RAM ####--  75% "


def test_compact_performance_lines_are_lcd_width():
    renderer = WidgetRenderer()

    lines = renderer.performance_bar_lines(
        100,
        100,
    )

    assert all(
        len(line) == LCD_WIDTH
        for line in lines
    )


def test_compact_performance_values_are_clamped():
    renderer = WidgetRenderer()

    line1, line2 = renderer.performance_bar_lines(
        -50,
        900,
    )

    assert line1 == "CPU ------   0% "
    assert line2 == "RAM ###### 100% "


def test_compact_performance_values_are_rounded():
    renderer = WidgetRenderer()

    line1, line2 = renderer.performance_bar_lines(
        49.6,
        24.5,
    )

    assert line1 == "CPU ###---  50% "
    assert line2 == "RAM #-----  24% "


def test_compact_performance_invalid_values_default_zero():
    renderer = WidgetRenderer()

    line1, line2 = renderer.performance_bar_lines(
        None,
        "warp-nine",
    )

    assert line1 == "CPU ------   0% "
    assert line2 == "RAM ------   0% "


def test_compact_performance_supports_block_style():
    renderer = WidgetRenderer()

    line = renderer.performance_bar_line(
        "CPU",
        50,
        style="blocks",
    )

    assert line == "CPU ███░░░  50% "


def test_compact_performance_requires_label():
    import pytest

    renderer = WidgetRenderer()

    with pytest.raises(
        ValueError,
        match="label is required",
    ):
        renderer.performance_bar_line(
            "",
            50,
        )


def test_compact_performance_requires_positive_width():
    import pytest

    renderer = WidgetRenderer()

    with pytest.raises(
        ValueError,
        match="greater than zero",
    ):
        renderer.performance_bar_line(
            "CPU",
            50,
            width=0,
        )


def test_compact_thermal_bar():
    renderer = WidgetRenderer()

    line = renderer.thermal_bar_line(
        50,
        minimum=20,
        maximum=80,
    )

    assert line == "TMP ###---  50% "


def test_compact_thermal_bar_clamps_low():
    renderer = WidgetRenderer()

    line = renderer.thermal_bar_line(
        -100,
        minimum=20,
        maximum=80,
    )

    assert line == "TMP ------   0% "


def test_compact_thermal_bar_clamps_high():
    renderer = WidgetRenderer()

    line = renderer.thermal_bar_line(
        500,
        minimum=20,
        maximum=80,
    )

    assert line == "TMP ###### 100% "


def test_compact_thermal_bar_invalid_value_defaults_low():
    renderer = WidgetRenderer()

    line = renderer.thermal_bar_line(
        "plasma",
        minimum=20,
        maximum=80,
    )

    assert line == "TMP ------   0% "


def test_compact_thermal_bar_supports_blocks():
    renderer = WidgetRenderer()

    line = renderer.thermal_bar_line(
        50,
        minimum=20,
        maximum=80,
        style="blocks",
    )

    assert line == "TMP ███░░░  50% "


def test_compact_thermal_bar_requires_valid_range():
    import pytest

    renderer = WidgetRenderer()

    with pytest.raises(
        ValueError,
        match="maximum must be greater",
    ):
        renderer.thermal_bar_line(
            50,
            minimum=80,
            maximum=20,
        )


def test_compact_thermal_bar_requires_positive_width():
    import pytest

    renderer = WidgetRenderer()

    with pytest.raises(
        ValueError,
        match="greater than zero",
    ):
        renderer.thermal_bar_line(
            50,
            width=0,
        )


def test_history_line_renders_sparkline():
    renderer = WidgetRenderer()

    line = renderer.history_line(
        "ACT",
        [0.0, 0.5, 1.0],
        width=12,
    )

    assert line == "ACT ..........+@"


def test_history_line_keeps_latest_samples():
    renderer = WidgetRenderer()

    line = renderer.history_line(
        "NET",
        [1.0] * 20,
        width=12,
    )

    assert line == "NET @@@@@@@@@@@@"


def test_history_line_requires_label():
    import pytest

    renderer = WidgetRenderer()

    with pytest.raises(
        ValueError,
        match="label is required",
    ):
        renderer.history_line(
            "",
            [0.5],
        )


def test_history_line_requires_positive_width():
    import pytest

    renderer = WidgetRenderer()

    with pytest.raises(
        ValueError,
        match="greater than zero",
    ):
        renderer.history_line(
            "ACT",
            [0.5],
            width=0,
        )


def test_history_line_supports_unicode_preview():
    renderer = WidgetRenderer()

    line = renderer.history_line(
        "ACT",
        [0.0, 0.5, 1.0],
        width=3,
        style="unicode",
    )

    assert line == "ACT ▁▅█         "


def test_history_line_rejects_unknown_style():
    import pytest

    renderer = WidgetRenderer()

    with pytest.raises(
        ValueError,
        match="style must be ascii or unicode",
    ):
        renderer.history_line(
            "ACT",
            [0.5],
            style="hieroglyphic",
        )
