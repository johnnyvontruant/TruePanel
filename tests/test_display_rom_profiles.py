import pytest

from truepanel.display.glyphs import GlyphMode
from truepanel.display.rom_profiles import (
    ROMGlyphProfile,
    parse_rom_byte,
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


def test_parse_rom_byte_accepts_integer():
    assert parse_rom_byte(255) == 0xFF


def test_parse_rom_byte_accepts_hex_string():
    assert parse_rom_byte("0xF4") == 0xF4


def test_parse_rom_byte_accepts_decimal_string():
    assert parse_rom_byte("244") == 244


def test_parse_rom_byte_rejects_out_of_range():
    with pytest.raises(
        ValueError,
        match="between 0x00 and 0xFF",
    ):
        parse_rom_byte(0x100)


def test_profile_requires_eight_levels():
    with pytest.raises(
        ValueError,
        match="exactly eight",
    ):
        ROMGlyphProfile.from_values(
            [0x20, 0xFF]
        )


def test_profile_builds_rom_glyph_manager():
    profile = ROMGlyphProfile.from_values(
        LEVELS
    )

    manager = profile.manager()

    assert manager.mode is GlyphMode.ROM
    assert manager.rom_levels == LEVELS


def test_profile_loads_from_config():
    profile = ROMGlyphProfile.from_config(
        {
            "graphics_engine": {
                "rom_levels": [
                    "0x20",
                    "0xF1",
                    "0xF2",
                    "0xF3",
                    "0xF4",
                    "0xF5",
                    "0xF6",
                    "0xFF",
                ]
            }
        }
    )

    assert profile.levels == LEVELS


def test_profile_serializes_hex_values():
    profile = ROMGlyphProfile.from_values(
        LEVELS,
        name="test-rom",
    )

    payload = profile.as_dict()

    assert payload["name"] == "test-rom"
    assert payload["levels_hex"] == [
        "0x20",
        "0xF1",
        "0xF2",
        "0xF3",
        "0xF4",
        "0xF5",
        "0xF6",
        "0xFF",
    ]
