"""
Project Stargate Glyph Atlas Runner.

Displays deterministic pages from the LCD character ROM atlas using only
documented display-write commands.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from truepanel.lab.glyph_atlas import (
    GlyphAtlasPage,
    atlas_page,
)


@dataclass(frozen=True)
class GlyphRunResult:
    page: GlyphAtlasPage
    success: bool

    def as_dict(self):
        return {
            "page": self.page.as_dict(),
            "success": self.success,
        }


class GlyphAtlasRunner:
    """Execute safe glyph atlas display experiments."""

    def __init__(self, controller):
        self.controller = controller

    def display_page(
        self,
        page_index: int,
    ) -> GlyphRunResult:
        page = atlas_page(page_index)

        self.controller.write_frame(
            page.line1,
            page.line2,
        )

        return GlyphRunResult(
            page=page,
            success=True,
        )

    def display_all(
        self,
        *,
        delay: float = 2.0,
        callback=None,
    ):
        results = []

        for index in range(8):
            result = self.display_page(index)

            results.append(result)

            if callback is not None:
                callback(result)

            if index != 7:
                time.sleep(delay)

        return results
