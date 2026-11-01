"""
Project Stargate LCD ROM Glyph Atlas.

Builds deterministic pages of raw LCD character bytes for safe visual
character-ROM discovery. This module defines atlas data only and performs
no hardware access.
"""

from __future__ import annotations

from dataclasses import dataclass


GLYPHS_PER_ROW = 16
ROWS_PER_PAGE = 2
GLYPHS_PER_PAGE = GLYPHS_PER_ROW * ROWS_PER_PAGE
BYTE_MIN = 0x00
BYTE_MAX = 0xFF


@dataclass(frozen=True)
class GlyphAtlasPage:
    """One two-row page of sequential LCD character bytes."""

    index: int
    start: int
    line1: bytes
    line2: bytes

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("page index must be non-negative")

        if not BYTE_MIN <= self.start <= BYTE_MAX:
            raise ValueError("page start must fit in one byte")

        if len(self.line1) != GLYPHS_PER_ROW:
            raise ValueError(
                f"line1 must contain {GLYPHS_PER_ROW} bytes"
            )

        if len(self.line2) != GLYPHS_PER_ROW:
            raise ValueError(
                f"line2 must contain {GLYPHS_PER_ROW} bytes"
            )

    @property
    def end(self) -> int:
        """Return the final byte value represented by this page."""

        return self.start + GLYPHS_PER_PAGE - 1

    @property
    def label(self) -> str:
        """Return a compact hexadecimal page range."""

        return f"0x{self.start:02X}-0x{self.end:02X}"

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "start": self.start,
            "start_hex": f"0x{self.start:02X}",
            "end": self.end,
            "end_hex": f"0x{self.end:02X}",
            "label": self.label,
            "line1": list(self.line1),
            "line2": list(self.line2),
            "line1_hex": self.line1.hex(" ").upper(),
            "line2_hex": self.line2.hex(" ").upper(),
        }


def build_page(start: int) -> GlyphAtlasPage:
    """Build one aligned 32-byte atlas page."""

    if not BYTE_MIN <= start <= BYTE_MAX:
        raise ValueError("page start must fit in one byte")

    if start % GLYPHS_PER_PAGE != 0:
        raise ValueError(
            f"page start must be aligned to {GLYPHS_PER_PAGE} bytes"
        )

    if start + GLYPHS_PER_PAGE - 1 > BYTE_MAX:
        raise ValueError("page exceeds the byte range")

    payload = bytes(
        range(start, start + GLYPHS_PER_PAGE)
    )

    return GlyphAtlasPage(
        index=start // GLYPHS_PER_PAGE,
        start=start,
        line1=payload[:GLYPHS_PER_ROW],
        line2=payload[GLYPHS_PER_ROW:],
    )


def build_atlas(
    *,
    start: int = BYTE_MIN,
    end: int = BYTE_MAX,
) -> tuple[GlyphAtlasPage, ...]:
    """Build aligned atlas pages covering an inclusive byte range."""

    if not BYTE_MIN <= start <= BYTE_MAX:
        raise ValueError("start must fit in one byte")

    if not BYTE_MIN <= end <= BYTE_MAX:
        raise ValueError("end must fit in one byte")

    if start > end:
        raise ValueError("start must not exceed end")

    first_page = (start // GLYPHS_PER_PAGE) * GLYPHS_PER_PAGE
    last_page = (end // GLYPHS_PER_PAGE) * GLYPHS_PER_PAGE

    return tuple(
        build_page(page_start)
        for page_start in range(
            first_page,
            last_page + 1,
            GLYPHS_PER_PAGE,
        )
    )


def atlas_page(index: int) -> GlyphAtlasPage:
    """Return one of the eight canonical 32-byte atlas pages."""

    if not 0 <= index < 8:
        raise ValueError("atlas page index must be between 0 and 7")

    return build_page(index * GLYPHS_PER_PAGE)
