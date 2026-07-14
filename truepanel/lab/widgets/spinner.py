"""
Reusable LCD spinner widget.
"""

from __future__ import annotations

from dataclasses import dataclass

from truepanel.lab.widgets.base import Widget


ASCII_FRAMES = (
    "|",
    "/",
    "-",
    "\\",
)

BLOCK_FRAMES = (
    "◜",
    "◝",
    "◞",
    "◟",
)


@dataclass(frozen=True)
class Spinner(Widget):
    frames: tuple[str, ...] = ASCII_FRAMES

    def render(
        self,
        frame: int,
    ) -> str:
        if not self.frames:
            raise ValueError(
                "spinner requires at least one frame"
            )

        return self.frames[
            frame % len(self.frames)
        ]

    @property
    def frame_count(self) -> int:
        return len(self.frames)
