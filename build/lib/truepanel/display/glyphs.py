"""
TruePanel graphics and glyph capability layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class GlyphMode(str, Enum):
    ASCII = "ascii"
    ROM = "rom"
    CUSTOM = "custom"


ASCII_LEVELS = (
    ord(" "),
    ord("."),
    ord(":"),
    ord("-"),
    ord("="),
    ord("+"),
    ord("*"),
    ord("#"),
)

ASCII_ICONS = {
    "healthy": ord("O"),
    "info": ord("i"),
    "warning": ord("!"),
    "critical": ord("X"),
    "temperature": ord("T"),
    "network": ord("N"),
    "storage": ord("D"),
    "cpu": ord("C"),
    "memory": ord("M"),
    "up": ord("^"),
    "down": ord("v"),
    "right": ord(">"),
    "left": ord("<"),
}


@dataclass(frozen=True)
class GlyphCapabilities:
    mode: GlyphMode = GlyphMode.ASCII
    raw_bytes: bool = True
    custom_characters: bool = False
    custom_slots: int = 0
    board_id: int | None = None
    protocol_version: int | None = None


class CustomGlyphUnavailable(RuntimeError):
    pass


class GlyphManager:
    def __init__(
        self,
        capabilities=None,
        rom_levels: Iterable[int] | None = None,
        custom_levels: Iterable[int] | None = None,
        icon_map=None,
    ):
        self.capabilities = capabilities or GlyphCapabilities()
        self.rom_levels = tuple(rom_levels or ())
        self.custom_levels = tuple(custom_levels or range(8))
        self.icon_map = dict(ASCII_ICONS)
        self.icon_map.update(icon_map or {})

    @property
    def mode(self):
        return self.capabilities.mode

    def level(self, index):
        index = max(0, min(7, int(index)))

        if (
            self.mode == GlyphMode.CUSTOM
            and self.capabilities.custom_characters
            and len(self.custom_levels) >= 8
        ):
            return self.custom_levels[index]

        if (
            self.mode == GlyphMode.ROM
            and len(self.rom_levels) >= 8
        ):
            return self.rom_levels[index]

        return ASCII_LEVELS[index]

    def icon(self, name, default="?"):
        value = self.icon_map.get(name)

        if value is None:
            return ord(default[:1] or "?")

        return int(value) & 0xFF

    @staticmethod
    def _numbers(values):
        result = []

        for value in values or []:
            try:
                result.append(float(value))
            except (TypeError, ValueError):
                result.append(0.0)

        return result

    @staticmethod
    def _downsample(values, width):
        if len(values) <= width:
            return values

        bucket_size = len(values) / width
        result = []

        for index in range(width):
            start = int(index * bucket_size)
            end = int((index + 1) * bucket_size)

            if end <= start:
                end = start + 1

            bucket = values[start:end]

            if bucket:
                result.append(sum(bucket) / len(bucket))

        return result

    def vertical_bar_graph(
        self,
        values,
        width=16,
        minimum=None,
        maximum=None,
    ):
        width = max(1, int(width))
        values = self._numbers(values)

        if not values:
            return bytes([self.level(0)] * width)

        values = self._downsample(values, width)[-width:]

        low = min(values) if minimum is None else float(minimum)
        high = max(values) if maximum is None else float(maximum)
        spread = high - low

        output = []

        for value in values:
            if spread <= 0:
                level = 4
            else:
                ratio = max(0.0, min(1.0, (value - low) / spread))
                level = int(round(ratio * 7))

            output.append(self.level(level))

        return bytes(
            [self.level(0)] * (width - len(output))
            + output
        )

    def horizontal_bar(
        self,
        percent,
        width=16,
    ):
        try:
            percent = max(0.0, min(100.0, float(percent)))
        except (TypeError, ValueError):
            percent = 0.0

        width = max(1, int(width))
        total_eighths = int(round(percent / 100 * width * 8))

        result = []

        for cell in range(width):
            remaining = total_eighths - (cell * 8)
            level = max(0, min(7, remaining))
            result.append(self.level(level))

        return bytes(result)

    def thermometer(
        self,
        temperature,
        minimum=20,
        maximum=70,
        width=12,
    ):
        try:
            temperature = float(temperature)
        except (TypeError, ValueError):
            temperature = float(minimum)

        spread = max(1.0, float(maximum) - float(minimum))
        percent = (
            (temperature - float(minimum))
            / spread
            * 100.0
        )

        return self.horizontal_bar(percent, width=width)

    def require_custom_support(self):
        if not self.capabilities.custom_characters:
            raise CustomGlyphUnavailable(
                "A125 custom-glyph programming has not been verified"
            )
