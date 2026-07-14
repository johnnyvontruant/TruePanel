"""
High-level widget renderer for Project Stargate.

Provides a stable interface between production dashboard pages and the
reusable widget library.
"""

from __future__ import annotations

from truepanel.lab.widgets import (
    BatteryMeter,
    ProgressBar,
    SignalMeter,
    Sparkline,
    Spinner,
    Thermometer,
)


LCD_WIDTH = 16


class WidgetRenderer:
    """High-level rendering facade for LCD widgets."""

    def cpu(
        self,
        percent: float,
        *,
        width: int = 8,
    ) -> str:
        return ProgressBar(
            width=width,
            style="ascii",
        ).render_percent(percent)

    def ram(
        self,
        percent: float,
        *,
        width: int = 8,
    ) -> str:
        return ProgressBar(
            width=width,
            style="ascii",
        ).render_percent(percent)

    def temp(
        self,
        degrees: float,
        *,
        width: int = 16,
    ) -> str:
        return Thermometer(
            width=width,
            style="ascii",
        ).render_temperature(degrees)

    def battery_level(
        self,
        percent: float,
        *,
        width: int = 16,
    ) -> str:
        return BatteryMeter(
            width=width,
            style="ascii",
        ).render_charge(percent)

    def signal_strength(
        self,
        value: float,
        *,
        width: int = 16,
    ) -> str:
        return SignalMeter(
            width=width,
            style="ascii",
        ).render(value)

    def history(self, values) -> str:
        return Sparkline().render(values)

    def activity(self, frame: int) -> str:
        return Spinner().render(frame)

    @staticmethod
    def _percentage(value: float) -> int:
        try:
            value = round(float(value))
        except (TypeError, ValueError):
            value = 0

        return max(0, min(100, value))

    def performance_lines(
        self,
        cpu_percent: float,
        ram_percent: float,
    ) -> tuple[str, str]:
        """Render clean percentage-only CPU and RAM rows."""

        cpu = self._percentage(cpu_percent)
        ram = self._percentage(ram_percent)

        line1 = f"CPU Usage {cpu:>3}%"
        line2 = f"RAM Usage {ram:>3}%"

        return (
            line1[:LCD_WIDTH].ljust(LCD_WIDTH),
            line2[:LCD_WIDTH].ljust(LCD_WIDTH),
        )


renderer = WidgetRenderer()
