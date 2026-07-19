import pytest

from truepanel.display.instruments import (
    DualTrendWidget,
    InstrumentPage,
    InstrumentTrend,
    MetricTrendWidget,
    PerformanceTrendWidget,
)
from truepanel.display.native_renderer import (
    NativeInstrumentFrame,
)


class RecordingTrendRenderer:
    def __init__(self):
        self.calls = []

    def trend_line(
        self,
        label,
        values,
        *args,
        **kwargs,
    ):
        values = tuple(values)

        self.calls.append(
            {
                "label": label,
                "values": values,
                "args": args,
                "kwargs": kwargs,
            }
        )

        summary = (
            f"{label}:{len(values)}"
            .encode("ascii")
        )

        return summary.ljust(
            16,
            b" ",
        )[:16]


def test_metric_trend_widget_builds_titled_page():
    renderer = RecordingTrendRenderer()

    widget = MetricTrendWidget(
        title="CPU HISTORY",
        label="cpu",
        history=[
            10,
            20,
            40,
        ],
        renderer=renderer,
    )

    page = widget.page()

    assert isinstance(
        page,
        InstrumentPage,
    )
    assert page.title == "CPU HISTORY"
    assert len(page.instruments) == 1
    assert isinstance(
        page.instruments[0],
        InstrumentTrend,
    )


def test_metric_trend_widget_renders_history():
    renderer = RecordingTrendRenderer()

    frame = MetricTrendWidget(
        title="CPU HISTORY",
        label="cpu",
        history=[
            10,
            20,
            40,
        ],
        renderer=renderer,
    ).render()

    assert isinstance(
        frame,
        NativeInstrumentFrame,
    )

    assert frame.line1 == b"CPU HISTORY     "
    assert frame.line2 == b"CPU:3           "

    assert renderer.calls == [
        {
            "label": "CPU",
            "values": (
                10.0,
                20.0,
                40.0,
            ),
            "args": (),
            "kwargs": {},
        }
    ]


def test_metric_trend_accepts_empty_history():
    renderer = RecordingTrendRenderer()

    frame = MetricTrendWidget(
        title="NETWORK",
        label="rx",
        history=[],
        renderer=renderer,
    ).render()

    assert frame.line1 == b"NETWORK         "
    assert frame.line2 == b"RX:0            "


def test_metric_trend_normalizes_numeric_strings():
    renderer = RecordingTrendRenderer()

    MetricTrendWidget(
        title="LOAD",
        label="cpu",
        history=[
            "10",
            "25.5",
            None,
        ],
        renderer=renderer,
    ).render()

    assert renderer.calls[0]["values"] == (
        10.0,
        25.5,
        0.0,
    )


def test_metric_trend_rejects_string_history():
    with pytest.raises(
        TypeError,
        match="numeric sequence",
    ):
        MetricTrendWidget(
            title="LOAD",
            label="cpu",
            history="10,20,30",
        )


def test_metric_trend_requires_title():
    with pytest.raises(
        ValueError,
        match="title is required",
    ):
        MetricTrendWidget(
            title="",
            label="cpu",
            history=[],
        )


def test_metric_trend_requires_label():
    with pytest.raises(
        ValueError,
        match="label is required",
    ):
        MetricTrendWidget(
            title="LOAD",
            label="",
            history=[],
        )


def test_dual_trend_widget_uses_both_rows():
    renderer = RecordingTrendRenderer()

    frame = DualTrendWidget(
        first_label="rx",
        first_history=[
            1,
            2,
            3,
        ],
        second_label="tx",
        second_history=[
            4,
            5,
        ],
        renderer=renderer,
        title="NETWORK",
    ).render()

    assert frame.line1 == b"RX:3            "
    assert frame.line2 == b"TX:2            "

    assert renderer.calls == [
        {
            "label": "RX",
            "values": (
                1.0,
                2.0,
                3.0,
            ),
            "args": (),
            "kwargs": {},
        },
        {
            "label": "TX",
            "values": (
                4.0,
                5.0,
            ),
            "args": (),
            "kwargs": {},
        },
    ]


def test_performance_trend_widget_uses_cpu_and_ram():
    renderer = RecordingTrendRenderer()

    frame = PerformanceTrendWidget(
        cpu_history=[
            20,
            40,
            60,
        ],
        ram_history=[
            30,
            35,
            40,
        ],
        renderer=renderer,
    ).render()

    assert frame.line1 == b"CPU:3           "
    assert frame.line2 == b"RAM:3           "

    assert [
        call["label"]
        for call in renderer.calls
    ] == [
        "CPU",
        "RAM",
    ]


def test_native_trend_rows_remain_exact_width():
    frame = PerformanceTrendWidget(
        cpu_history=[
            0,
            20,
            40,
            60,
            80,
            100,
        ],
        ram_history=[
            100,
            80,
            60,
            40,
            20,
            0,
        ],
    ).render()

    assert len(frame.line1) == 16
    assert len(frame.line2) == 16
