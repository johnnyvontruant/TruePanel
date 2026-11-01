"""
Reusable LCD thermometer widget.
"""

from __future__ import annotations

from dataclasses import dataclass

from truepanel.lab.widgets.linear import LinearWidget


@dataclass(frozen=True)
class Thermometer(LinearWidget):
    minimum: float = 0.0
    maximum: float = 100.0
    style: str = "blocks"

    def render_temperature(
        self,
        value: float,
    ) -> str:
        return self.render(value)
