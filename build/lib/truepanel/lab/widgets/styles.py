"""
Rendering styles for LCD widgets.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BarStyle:
    name: str
    filled: str
    empty: str


ASCII = BarStyle(
    "ascii",
    "#",
    "-",
)

BLOCKS = BarStyle(
    "blocks",
    "█",
    "░",
)

DOTS = BarStyle(
    "dots",
    "•",
    "·",
)


STYLES = {
    style.name: style
    for style in (
        ASCII,
        BLOCKS,
        DOTS,
    )
}


def get_style(name: str) -> BarStyle:
    try:
        return STYLES[name]
    except KeyError:
        raise ValueError(
            f"Unknown widget style: {name}"
        )
