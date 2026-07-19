import pytest

from truepanel.display.instruments import (
    CapacityWidget,
    InstrumentPage,
    OperationWidget,
    PerformanceWidget,
    ThermalWidget,
)
from truepanel.display.native_renderer import (
    NativeInstrumentFrame,
    NativeInstrumentRenderer,
)


def ascii_renderer():
    return NativeInstrumentRenderer(
        raw_blocks=False,
    )


def test_performance_widget_builds_instrument_page():
    widget = PerformanceWidget(
        64,
        32,
        renderer=ascii_renderer(),
    )

    page = widget.page()

    assert isinstance(
        page,
        InstrumentPage,
    )
    assert page.title == "PERFORMANCE"
    assert len(page.instruments) == 2


def test_performance_widget_renders_cpu_and_ram():
    frame = PerformanceWidget(
        64,
        32,
        renderer=ascii_renderer(),
    ).render()

    assert isinstance(
        frame,
        NativeInstrumentFrame,
    )
    assert frame.line1 == b"CPU ####--  64% "
    assert frame.line2 == b"RAM ##----  32% "


def test_performance_widget_clamps_values():
    frame = PerformanceWidget(
        200,
        -20,
        renderer=ascii_renderer(),
    ).render()

    assert frame.line1 == b"CPU ###### 100% "
    assert frame.line2 == b"RAM ------   0% "


def test_capacity_widget_builds_pool_title():
    frame = CapacityWidget(
        "tank",
        82,
        renderer=ascii_renderer(),
    ).render()

    assert frame.line1 == b"POOL tank    82%"
    assert frame.line2 == b"USE #####-  82% "


def test_capacity_widget_accepts_percent_string():
    frame = CapacityWidget(
        "backup",
        "45%",
        renderer=ascii_renderer(),
    ).render()

    assert frame.line1 == b"POOL backup  45%"
    assert frame.line2 == b"USE ###---  45% "


def test_capacity_widget_requires_pool():
    with pytest.raises(
        ValueError,
        match="pool is required",
    ):
        CapacityWidget(
            "",
            50,
        )


def test_thermal_widget_normalizes_temperature():
    widget = ThermalWidget(
        "sdb",
        50,
        minimum=20,
        maximum=80,
        renderer=ascii_renderer(),
    )

    assert widget.normalized_percent == 50

    frame = widget.render()

    assert frame.line1 == b"TEMP sdb   50C  "
    assert frame.line2 == b"TMP ###---  50% "


def test_thermal_widget_clamps_below_minimum():
    frame = ThermalWidget(
        "sda",
        0,
        minimum=20,
        maximum=80,
        renderer=ascii_renderer(),
    ).render()

    assert frame.line2 == b"TMP ------   0% "


def test_thermal_widget_clamps_above_maximum():
    frame = ThermalWidget(
        "sda",
        100,
        minimum=20,
        maximum=80,
        renderer=ascii_renderer(),
    ).render()

    assert frame.line2 == b"TMP ###### 100% "


def test_thermal_widget_rejects_invalid_range():
    with pytest.raises(
        ValueError,
        match="maximum must be greater",
    ):
        ThermalWidget(
            "sda",
            40,
            minimum=80,
            maximum=20,
        )


def test_operation_widget_renders_scrub_progress():
    widget = OperationWidget(
        "scrub",
        42,
        renderer=ascii_renderer(),
    )

    assert widget.label == "SCR"

    frame = widget.render()

    assert frame.line1 == b"SCRUB ACTIVE    "
    assert frame.line2 == b"SCR ###---  42% "


def test_operation_widget_uses_resilver_abbreviation():
    widget = OperationWidget(
        "resilver",
        75,
        renderer=ascii_renderer(),
    )

    assert widget.label == "RSL"

    frame = widget.render()

    assert frame.line1 == b"RESILVER ACTIVE "
    assert frame.line2 == b"RSL #####-  75% "


def test_operation_widget_supports_custom_operation():
    widget = OperationWidget(
        "replication",
        25,
        renderer=ascii_renderer(),
    )

    assert widget.label == "REP"

    frame = widget.render()

    assert frame.line1 == b"REPLICATIO ACTIV"
    assert frame.line2 == b"REP ##----  25% "
