import pytest

from truepanel.display.native_renderer import (
    EMPTY_CELL,
    FULL_CELL,
    NativeInstrumentFrame,
    NativeInstrumentRenderer,
    clamp_percentage,
    fit_text,
)


def test_clamp_percentage():
    assert clamp_percentage(-5) == 0
    assert clamp_percentage(42.4) == 42
    assert clamp_percentage(500) == 100
    assert clamp_percentage("plasma") == 0


def test_fit_text_is_exact_width():
    assert fit_text("READY") == (
        b"READY" + b" " * 11
    )

    assert fit_text(
        "ABCDEFGHIJKLMNOPQRST"
    ) == b"ABCDEFGHIJKLMNOP"


def test_frame_requires_exact_width():
    with pytest.raises(
        ValueError,
        match="line1 must be exactly 16",
    ):
        NativeInstrumentFrame(
            b"short",
            b" " * 16,
        )


def test_native_bar_uses_full_block_byte():
    renderer = NativeInstrumentRenderer()

    assert renderer.bar(
        50,
        width=6,
    ) == (
        bytes([FULL_CELL]) * 3
        + bytes([EMPTY_CELL]) * 3
    )


def test_native_bar_clamps():
    renderer = NativeInstrumentRenderer()

    assert renderer.bar(
        -50,
        width=4,
    ) == b" " * 4

    assert renderer.bar(
        500,
        width=4,
    ) == bytes([FULL_CELL]) * 4


def test_ascii_bar_fallback():
    renderer = NativeInstrumentRenderer(
        raw_blocks=False
    )

    assert renderer.bar(
        50,
        width=6,
    ) == b"###---"


def test_half_cell_rounds_up():
    renderer = NativeInstrumentRenderer(
        raw_blocks=False
    )

    assert renderer.bar(
        75,
        width=6,
    ) == b"#####-"


def test_performance_frame():
    renderer = NativeInstrumentRenderer()

    frame = renderer.performance(
        50,
        75,
    )

    assert frame.line1 == (
        b"CPU "
        + bytes([FULL_CELL]) * 3
        + b" " * 3
        + b"  50% "
    )

    assert frame.line2 == (
        b"RAM "
        + bytes([FULL_CELL]) * 5
        + b" "
        + b"  75% "
    )

    assert len(frame.line1) == 16
    assert len(frame.line2) == 16


def test_performance_ascii_fallback():
    renderer = NativeInstrumentRenderer(
        raw_blocks=False
    )

    frame = renderer.performance(
        50,
        75,
    )

    assert frame.line1 == b"CPU ###---  50% "
    assert frame.line2 == b"RAM #####-  75% "


def test_thermal_frame():
    renderer = NativeInstrumentRenderer(
        raw_blocks=False
    )

    frame = renderer.thermal(
        "sda",
        50,
        minimum=20,
        maximum=80,
    )

    assert frame.line1 == b"TEMP sda   50C  "
    assert frame.line2 == b"TMP ###---  50% "


def test_capacity_frame():
    renderer = NativeInstrumentRenderer(
        raw_blocks=False
    )

    frame = renderer.capacity(
        "tank",
        82,
    )

    assert frame.line1 == b"POOL tank    82%"
    assert frame.line2 == b"USE #####-  82% "


def test_mission_frame():
    renderer = NativeInstrumentRenderer(
        raw_blocks=False
    )

    frame = renderer.mission()

    assert frame.line1 == b" MISSION READY  "
    assert frame.line2 == b"SYS ###### 100% "
