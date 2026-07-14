"""
Reusable LCD progress bar widget.
"""

from __future__ import annotations

from dataclasses import dataclass

from truepanel.lab.widgets.base import Widget
from truepanel.lab.widgets.styles import get_style


@dataclass(frozen=True)
class ProgressBar(Widget):
    style: str = "ascii"

    def render(
        self,
        value: float,
    ) -> str:
        value = max(0.0, min(1.0, value))

        style = get_style(self.style)

        filled = round(
            value * self.width
        )

        return (
            style.filled * filled
            + style.empty * (self.width - filled)
        )

    def render_percent(
        self,
        percent: float,
    ) -> str:
        return self.render(
            percent / 100.0
        )
