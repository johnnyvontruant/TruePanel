"""
Common linear-fill widget implementation.
"""

from __future__ import annotations

from dataclasses import dataclass

from truepanel.lab.widgets.base import Widget
from truepanel.lab.widgets.styles import get_style


@dataclass(frozen=True)
class LinearWidget(Widget):
    minimum: float = 0.0
    maximum: float = 1.0
    style: str = "blocks"

    def normalize(
        self,
        value: float,
    ) -> float:
        if self.maximum <= self.minimum:
            raise ValueError(
                "maximum must exceed minimum"
            )

        clamped = max(
            self.minimum,
            min(self.maximum, value),
        )

        return (
            (clamped - self.minimum)
            / (self.maximum - self.minimum)
        )

    def render(
        self,
        value: float,
    ) -> str:
        normalized = self.normalize(value)
        style = get_style(self.style)

        filled = round(
            normalized * self.width
        )

        return (
            style.filled * filled
            + style.empty * (self.width - filled)
        )
