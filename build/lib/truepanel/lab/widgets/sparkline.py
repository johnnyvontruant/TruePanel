"""
Reusable LCD sparkline widget.
"""

from __future__ import annotations

from dataclasses import dataclass

from truepanel.lab.widgets.base import Widget


LEVELS = (
    "▁",
    "▂",
    "▃",
    "▄",
    "▅",
    "▆",
    "▇",
    "█",
)


@dataclass(frozen=True)
class Sparkline(Widget):
    """
    Render normalized history values as Unicode sparklines.
    """

    def render(
        self,
        values,
    ) -> str:
        values = list(values)

        if not values:
            return ""

        result = []

        for value in values[-self.width:]:

            value = max(
                0.0,
                min(1.0, float(value)),
            )

            index = round(
                value * (len(LEVELS) - 1)
            )

            result.append(
                LEVELS[index]
            )

        return "".join(result)
