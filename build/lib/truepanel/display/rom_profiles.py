"""
Native LCD ROM graphics profiles.

A ROM profile maps eight visual fill levels, from empty through full, to
single-byte character codes already present in the LCD controller's ROM.

This module performs no hardware access.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .glyphs import (
    GlyphCapabilities,
    GlyphManager,
    GlyphMode,
)


LEVEL_COUNT = 8


def parse_rom_byte(value) -> int:
    """
    Parse one ROM byte from an integer or a decimal/hexadecimal string.
    """

    if isinstance(value, bool):
        raise TypeError("ROM byte cannot be boolean")

    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()

        if not text:
            raise ValueError("ROM byte cannot be empty")

        parsed = int(text, 0)
    else:
        raise TypeError(
            "ROM byte must be an integer or numeric string"
        )

    if not 0 <= parsed <= 0xFF:
        raise ValueError(
            "ROM byte must be between 0x00 and 0xFF"
        )

    return parsed


@dataclass(frozen=True)
class ROMGlyphProfile:
    """
    Eight ordered LCD ROM bytes representing increasing fill levels.
    """

    name: str
    levels: tuple[int, ...]

    def __post_init__(self):
        if not self.name or not self.name.strip():
            raise ValueError("profile name is required")

        normalized = tuple(
            parse_rom_byte(value)
            for value in self.levels
        )

        if len(normalized) != LEVEL_COUNT:
            raise ValueError(
                "ROM profile must contain exactly eight levels"
            )

        object.__setattr__(self, "levels", normalized)

    @classmethod
    def from_values(
        cls,
        values: Iterable,
        *,
        name="a125-rom",
    ):
        return cls(
            name=name,
            levels=tuple(values),
        )

    @classmethod
    def from_config(
        cls,
        config,
        *,
        name="a125-rom",
    ):
        config = config or {}
        graphics = config.get("graphics_engine", {})

        levels = graphics.get("rom_levels", ())

        return cls.from_values(
            levels,
            name=name,
        )

    def manager(self):
        capabilities = GlyphCapabilities(
            mode=GlyphMode.ROM,
            raw_bytes=True,
            custom_characters=False,
            custom_slots=0,
        )

        return GlyphManager(
            capabilities=capabilities,
            rom_levels=self.levels,
        )

    def as_dict(self):
        return {
            "name": self.name,
            "levels": list(self.levels),
            "levels_hex": [
                f"0x{value:02X}"
                for value in self.levels
            ],
        }
