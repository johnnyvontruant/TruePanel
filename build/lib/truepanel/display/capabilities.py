"""
TruePanel graphics capability detection.
"""

from __future__ import annotations

import logging

from .glyphs import GlyphCapabilities, GlyphMode


LOGGER = logging.getLogger("truepanel.display.capabilities")


def detect_graphics_capabilities(config=None, lcd=None):
    config = config or {}
    graphics = config.get("graphics_engine", {})

    requested = str(
        graphics.get("mode", "auto")
    ).lower()

    custom_verified = bool(
        graphics.get("custom_glyphs_verified", False)
    )

    rom_levels = graphics.get("rom_levels", [])

    if requested == "custom":
        if custom_verified:
            return GlyphCapabilities(
                mode=GlyphMode.CUSTOM,
                raw_bytes=True,
                custom_characters=True,
                custom_slots=8,
            )

        LOGGER.warning(
            "Custom glyph mode requested but A125 support "
            "is not verified; falling back"
        )

    if requested in ("rom", "auto") and len(rom_levels) >= 8:
        return GlyphCapabilities(
            mode=GlyphMode.ROM,
            raw_bytes=True,
            custom_characters=False,
            custom_slots=0,
        )

    return GlyphCapabilities(
        mode=GlyphMode.ASCII,
        raw_bytes=True,
        custom_characters=False,
        custom_slots=0,
    )
