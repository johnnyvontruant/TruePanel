from truepanel.display.graphics import (
    graph_frame,
    progress_frame,
    thermometer_frame,
)
from truepanel.display.rom_profiles import (
    ROMGlyphProfile,
)


LEVELS = (
    0x20,
    0xF1,
    0xF2,
    0xF3,
    0xF4,
    0xF5,
    0xF6,
    0xFF,
)


def glyphs():
    return ROMGlyphProfile.from_values(
        LEVELS
    ).manager()


def test_rom_progress_frame_uses_raw_bytes():
    frame = progress_frame(
        "CPU 50%",
        50,
        glyphs(),
        width=16,
    )

    line1, line2 = frame.lines

    assert line1 == b"CPU 50%         "
    assert isinstance(line2, bytes)
    assert len(line2) == 16
    assert set(line2).issubset(
        set(LEVELS)
    )


def test_rom_progress_frame_empty():
    frame = progress_frame(
        "CPU 0%",
        0,
        glyphs(),
        width=16,
    )

    assert frame.lines[1] == bytes(
        [LEVELS[0]] * 16
    )


def test_rom_progress_frame_full():
    frame = progress_frame(
        "CPU 100%",
        100,
        glyphs(),
        width=16,
    )

    assert frame.lines[1] == bytes(
        [LEVELS[7]] * 16
    )


def test_rom_graph_frame_preserves_width():
    frame = graph_frame(
        "HISTORY",
        [0.0, 0.5, 1.0],
        glyphs(),
        width=16,
    )

    assert len(frame.lines[0]) == 16
    assert len(frame.lines[1]) == 16


def test_rom_thermometer_frame_preserves_raw_payload():
    frame = thermometer_frame(
        "TEMP 50C",
        50,
        glyphs(),
        minimum=20,
        maximum=80,
    )

    assert isinstance(frame.lines[1], bytes)
    assert len(frame.lines[1]) == 16
