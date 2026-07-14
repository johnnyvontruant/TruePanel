"""
Reusable LCD signal-strength widget.
"""

from __future__ import annotations

from dataclasses import dataclass

from truepanel.lab.widgets.linear import LinearWidget


@dataclass(frozen=True)
class SignalMeter(LinearWidget):
    minimum: float = 0.0
    maximum: float = 1.0
    style: str = "blocks"

    def render_percent(
        self,
        percent: float,
    ) -> str:
        return self.render(
            percent / 100.0
        )
