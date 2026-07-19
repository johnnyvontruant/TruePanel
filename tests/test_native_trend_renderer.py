import pytest

from truepanel.display.instruments import (
    InstrumentTrend,
)
from truepanel.display.native_renderer import (
    NativeInstrumentRenderer,
)


def test_renderer_normalizes_absolute_history():
    renderer = NativeInstrumentRenderer()

    assert renderer.normalize_trend_values(
        [
            0,
            25,
            50,
            100,
        ],
        width=4,
    ) == [
        0.0,
        0.25,
        0.5,
        1.0,
    ]


def test_renderer_preserves_ratio_history():
    renderer = NativeInstrumentRenderer()

    assert renderer.normalize_trend_values(
        [
            0.1,
            0.5,
            1.0,
        ],
        width=3,
    ) == [
        0.1,
        0.5,
        1.0,
    ]


def test_renderer_left_pads_short_history():
    renderer = NativeInstrumentRenderer()

    assert renderer.normalize_trend_values(
        [
            50,
            100,
        ],
        width=4,
    ) == [
        0.0,
        0.0,
        0.5,
        1.0,
    ]


def test_renderer_returns_empty_trend_for_no_history():
    renderer = NativeInstrumentRenderer()

    assert renderer.normalize_trend_values(
        [],
        width=4,
    ) == [
        0.0,
        0.0,
        0.0,
        0.0,
    ]


def test_renderer_trend_line_matches_existing_format():
    renderer = NativeInstrumentRenderer()

    line = renderer.trend_line(
        "cpu",
        [
            0,
            20,
            40,
            60,
            80,
            100,
        ],
    )

    assert line == b"CPU   .-=*# 100%"
    assert len(line) == 16


def test_renderer_trend_line_handles_empty_history():
    renderer = NativeInstrumentRenderer()

    line = renderer.trend_line(
        "rx",
        [],
    )

    assert line == b"RX            0%"
    assert len(line) == 16


def test_renderer_rejects_oversized_trend():
    renderer = NativeInstrumentRenderer()

    with pytest.raises(
        ValueError,
        match="cannot exceed eight",
    ):
        renderer.trend_line(
            "cpu",
            [1],
            width=9,
        )


def test_instrument_trend_delegates_to_renderer():
    class RecordingRenderer:
        def __init__(self):
            self.calls = []

        def trend_line(
            self,
            label,
            values,
            *args,
            **kwargs,
        ):
            self.calls.append(
                (
                    label,
                    tuple(values),
                    args,
                    kwargs,
                )
            )

            return b"TREND           "

    renderer = RecordingRenderer()

    instrument = InstrumentTrend(
        "cpu",
        [
            10,
            20,
            30,
        ],
        renderer=renderer,
    )

    assert instrument.render_line() == (
        b"TREND           "
    )

    assert renderer.calls == [
        (
            "cpu",
            (
                10,
                20,
                30,
            ),
            (),
            {},
        )
    ]
