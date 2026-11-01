"""
Hardware-ready TruePanel LCD frames.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


LCD_WIDTH = 16
LineValue = Union[str, bytes, bytearray]


def normalize_raw(value: LineValue) -> bytes:
    if isinstance(value, bytearray):
        value = bytes(value)

    if isinstance(value, bytes):
        return value[:LCD_WIDTH].ljust(LCD_WIDTH, b" ")

    return (
        str(value)
        .encode("latin-1", errors="replace")[:LCD_WIDTH]
        .ljust(LCD_WIDTH, b" ")
    )


@dataclass(frozen=True)
class RawLCDFrame:
    line1: LineValue
    line2: LineValue

    @property
    def lines(self):
        return [
            normalize_raw(self.line1),
            normalize_raw(self.line2),
        ]


@dataclass(frozen=True)
class GraphicsFrame:
    title: str
    payload: bytes

    @property
    def lines(self):
        return [
            normalize_raw(self.title),
            normalize_raw(self.payload),
        ]
