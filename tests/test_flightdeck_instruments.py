import pytest

from truepanel.display.instruments import (
    InstrumentGauge,
    InstrumentPage,
    InstrumentProgress,
    InstrumentStatus,
    InstrumentTrend,
)
from truepanel.display.native_renderer import (
    FULL_CELL,
    NativeInstrumentFrame,
    NativeInstrumentRenderer,
)


def ascii_renderer():
    return NativeInstrumentRenderer(
        raw_blocks=False,
    )


def test_gauge_renders_exact_width_native_row():
    gauge = InstrumentGauge(
        "cpu",
        50,
    )

    line = gauge.render_line()

    assert len(line) == 16
    assert line.startswith(b"CPU ")
    assert bytes((FULL_CELL,)) in line
    assert line.endswith(b"  50% ")


def test_gauge_supports_ascii_fallback():
    gauge = InstrumentGauge(
        "ram",
        75,
        renderer=ascii_renderer(),
    )

    line = gauge.render_line()

    assert line == b"RAM #####-  75% "


def test_gauge_clamps_percentage():
    gauge = InstrumentGauge(
        "cpu",
        500,
        renderer=ascii_renderer(),
    )

    assert gauge.render_line() == b"CPU ###### 100% "


def test_gauge_requires_label():
    with pytest.raises(
        ValueError,
        match="label is required",
    ):
        InstrumentGauge(
            "",
            50,
        )


def test_progress_has_independent_semantic_type():
    progress = InstrumentProgress(
        "rsl",
        42,
        renderer=ascii_renderer(),
    )

    assert progress.render_line() == b"RSL ###---  42% "


def test_status_renders_label_and_value():
    status = InstrumentStatus(
        "pool",
        "online",
    )

    assert status.render_line() == b"POOL      ONLINE"


def test_status_truncates_long_value():
    status = InstrumentStatus(
        "state",
        "degraded-operation",
    )

    assert status.render_line() == b"STATE DEGRADED-O"


def test_status_requires_value():
    with pytest.raises(
        ValueError,
        match="status value is required",
    ):
        InstrumentStatus(
            "pool",
            "",
        )


def test_trend_normalizes_raw_values():
    trend = InstrumentTrend(
        "net",
        [0, 25, 50, 75, 100],
        width=5,
    )

    assert trend.normalized_values() == [
        0.0,
        0.25,
        0.5,
        0.75,
        1.0,
    ]


def test_trend_preserves_normalized_values():
    trend = InstrumentTrend(
        "act",
        [0.0, 0.25, 0.5, 1.0],
        width=4,
    )

    assert trend.normalized_values() == [
        0.0,
        0.25,
        0.5,
        1.0,
    ]


def test_trend_pads_short_history():
    trend = InstrumentTrend(
        "net",
        [1, 2],
        width=4,
    )

    assert trend.normalized_values() == [
        0.0,
        0.0,
        0.5,
        1.0,
    ]


def test_trend_renders_exact_width_row():
    trend = InstrumentTrend(
        "net",
        [0, 25, 50, 75, 100],
        width=7,
    )

    line = trend.render_line()

    assert len(line) == 16
    assert line.startswith(b"NET ")
    assert line.endswith(b"100%")


def test_empty_page_renders_title_and_blank_row():
    frame = InstrumentPage(
        "FLIGHT DECK",
    ).render()

    assert isinstance(
        frame,
        NativeInstrumentFrame,
    )
    assert frame.line1 == b"FLIGHT DECK     "
    assert frame.line2 == b"                "


def test_single_instrument_page_uses_title_row():
    page = InstrumentPage(
        "STORAGE",
    )

    page.add(
        InstrumentStatus(
            "pool",
            "online",
        )
    )

    frame = page.render()

    assert frame.line1 == b"STORAGE         "
    assert frame.line2 == b"POOL      ONLINE"


def test_two_instrument_page_uses_both_rows():
    page = InstrumentPage(
        "PERFORMANCE",
    )

    page.add(
        InstrumentGauge(
            "cpu",
            50,
            renderer=ascii_renderer(),
        )
    )
    page.add(
        InstrumentGauge(
            "ram",
            25,
            renderer=ascii_renderer(),
        )
    )

    frame = page.render()

    assert frame.line1 == b"CPU ###---  50% "
    assert frame.line2 == b"RAM ##----  25% "


def test_page_add_is_chainable():
    page = InstrumentPage(
        "SYSTEM",
    )

    result = page.add(
        InstrumentStatus(
            "mode",
            "ready",
        )
    )

    assert result is page


def test_page_rejects_non_instrument():
    page = InstrumentPage(
        "SYSTEM",
    )

    with pytest.raises(
        TypeError,
        match="Instrument instances",
    ):
        page.add("not an instrument")


def test_page_rejects_third_instrument():
    page = InstrumentPage(
        "SYSTEM",
    )

    page.add(
        InstrumentStatus(
            "one",
            "ready",
        )
    )
    page.add(
        InstrumentStatus(
            "two",
            "ready",
        )
    )

    with pytest.raises(
        ValueError,
        match="at most two",
    ):
        page.add(
            InstrumentStatus(
                "three",
                "ready",
            )
        )
