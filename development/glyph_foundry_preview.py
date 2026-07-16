#!/usr/bin/env python3
"""
Offline preview of Project Stargate custom glyphs.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from truepanel.lab.protocol import (
    VERTICAL_FILL_GLYPHS,
    all_glyphs,
)


def show(item):
    print("=" * 17)
    print(item.name)
    print("=" * 17)
    print(item.preview())
    print(
        "Rows:",
        " ".join(item.row_hex),
    )
    print()


def main():
    print(
        "Project Stargate Custom Glyph Foundry"
    )
    print()

    for item in VERTICAL_FILL_GLYPHS:
        show(item)

    for item in all_glyphs():
        if item.name not in {
            glyph.name
            for glyph in VERTICAL_FILL_GLYPHS
        }:
            show(item)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
