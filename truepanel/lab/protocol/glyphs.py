"""
Custom 5x8 glyph models for Project Stargate.

A custom glyph contains exactly eight rows. Each row uses only the lower five
bits, matching a standard 5x8 character-cell bitmap.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


GLYPH_WIDTH = 5
GLYPH_HEIGHT = 8
ROW_MAX = (1 << GLYPH_WIDTH) - 1


def normalize_row(value) -> int:
    if isinstance(value, bool):
        raise TypeError(
            "glyph row cannot be boolean"
        )

    try:
        row = int(value)
    except (TypeError, ValueError) as error:
        raise TypeError(
            "glyph row must be an integer"
        ) from error

    if not 0 <= row <= ROW_MAX:
        raise ValueError(
            "glyph row must fit within five bits"
        )

    return row


@dataclass(frozen=True)
class CustomGlyph:
    """
    Immutable 5x8 custom character bitmap.
    """

    name: str
    rows: tuple[int, ...]

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(
                "glyph name is required"
            )

        normalized = tuple(
            normalize_row(row)
            for row in self.rows
        )

        if len(normalized) != GLYPH_HEIGHT:
            raise ValueError(
                "glyph must contain exactly eight rows"
            )

        object.__setattr__(
            self,
            "name",
            self.name.strip(),
        )
        object.__setattr__(
            self,
            "rows",
            normalized,
        )

    @classmethod
    def from_rows(
        cls,
        name: str,
        rows: Iterable[int],
    ):
        return cls(
            name=name,
            rows=tuple(rows),
        )

    @property
    def payload(self) -> bytes:
        return bytes(self.rows)

    @property
    def row_hex(self):
        return tuple(
            f"0x{row:02X}"
            for row in self.rows
        )

    def preview(
        self,
        *,
        on="#",
        off=".",
    ) -> str:
        if not on:
            raise ValueError(
                "on preview character is required"
            )

        if not off:
            raise ValueError(
                "off preview character is required"
            )

        on = str(on)[0]
        off = str(off)[0]

        lines = []

        for row in self.rows:
            line = "".join(
                on
                if row & (1 << bit)
                else off
                for bit in range(
                    GLYPH_WIDTH - 1,
                    -1,
                    -1,
                )
            )
            lines.append(line)

        return "\n".join(lines)

    def as_dict(self):
        return {
            "name": self.name,
            "width": GLYPH_WIDTH,
            "height": GLYPH_HEIGHT,
            "rows": list(self.rows),
            "rows_hex": list(self.row_hex),
            "preview": self.preview(),
        }
