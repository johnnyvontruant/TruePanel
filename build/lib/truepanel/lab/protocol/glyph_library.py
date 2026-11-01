"""
Built-in custom glyph library.
"""

from __future__ import annotations

from types import MappingProxyType

from .glyphs import CustomGlyph


EMPTY_ROW = 0b00000
FULL_ROW = 0b11111


def vertical_fill_level(level: int) -> CustomGlyph:
    """
    Return a glyph filled upward from the bottom.

    Levels range from zero through seven. Level seven is a fully filled cell.
    """

    try:
        level = int(level)
    except (TypeError, ValueError) as error:
        raise TypeError(
            "fill level must be an integer"
        ) from error

    if not 0 <= level <= 7:
        raise ValueError(
            "fill level must be between zero and seven"
        )

    filled_rows = (
        0
        if level == 0
        else level + 1
    )

    empty_rows = 8 - filled_rows

    return CustomGlyph.from_rows(
        f"vertical-fill-{level}",
        (
            [EMPTY_ROW] * empty_rows
            + [FULL_ROW] * filled_rows
        ),
    )


VERTICAL_FILL_GLYPHS = tuple(
    vertical_fill_level(level)
    for level in range(8)
)


GLYPHS = MappingProxyType(
    {
        "blank": CustomGlyph.from_rows(
            "blank",
            [EMPTY_ROW] * 8,
        ),
        "full": CustomGlyph.from_rows(
            "full",
            [FULL_ROW] * 8,
        ),
        "check": CustomGlyph.from_rows(
            "check",
            (
                0b00000,
                0b00000,
                0b00001,
                0b00010,
                0b10100,
                0b01000,
                0b00000,
                0b00000,
            ),
        ),
        "warning": CustomGlyph.from_rows(
            "warning",
            (
                0b00100,
                0b01110,
                0b01110,
                0b11111,
                0b11011,
                0b11111,
                0b11111,
                0b00000,
            ),
        ),
        "up": CustomGlyph.from_rows(
            "up",
            (
                0b00100,
                0b01110,
                0b10101,
                0b00100,
                0b00100,
                0b00100,
                0b00100,
                0b00000,
            ),
        ),
        "down": CustomGlyph.from_rows(
            "down",
            (
                0b00000,
                0b00100,
                0b00100,
                0b00100,
                0b00100,
                0b10101,
                0b01110,
                0b00100,
            ),
        ),
    }
)


def glyph(name: str) -> CustomGlyph:
    try:
        return GLYPHS[name]
    except KeyError as error:
        raise KeyError(
            f"unknown built-in glyph: {name}"
        ) from error


def all_glyphs():
    return tuple(GLYPHS.values())
