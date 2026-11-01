"""
Project Stargate Display Pattern Library.

Provides deterministic LCD patterns for repeatable display experiments.
"""

from __future__ import annotations

from dataclasses import dataclass


DISPLAY_WIDTH = 16


@dataclass(frozen=True)
class DisplayPattern:
    """One deterministic display pattern."""

    name: str
    line1: str
    line2: str

    def __post_init__(self):
        if len(self.line1) != DISPLAY_WIDTH:
            raise ValueError(
                f"line1 must be exactly {DISPLAY_WIDTH} characters"
            )

        if len(self.line2) != DISPLAY_WIDTH:
            raise ValueError(
                f"line2 must be exactly {DISPLAY_WIDTH} characters"
            )


_PATTERNS = (
    DisplayPattern(
        "alphabet",
        "ABCDEFGHIJKLMNOP",
        "QRSTUVWXYZ012345",
    ),
    DisplayPattern(
        "numbers",
        "0123456789ABCDEF",
        "FEDCBA9876543210",
    ),
    DisplayPattern(
        "checker",
        "A1B2C3D4E5F6G7H8",
        "8H7G6F5E4D3C2B1A",
    ),
    DisplayPattern(
        "solid",
        "################",
        "................",
    ),
)


def patterns() -> tuple[DisplayPattern, ...]:
    """Return every built-in display pattern."""
    return _PATTERNS


def pattern(name: str) -> DisplayPattern:
    """Return one pattern by name."""

    for candidate in _PATTERNS:
        if candidate.name == name:
            return candidate

    raise KeyError(name)
