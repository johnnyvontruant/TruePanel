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
        """Render CPU utilization using an ASCII-safe progress bar."""

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
        """Render RAM utilization using an ASCII-safe progress bar."""

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
        """Render a temperature in degrees Celsius."""

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
        """Render UPS battery percentage."""

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
        """Render normalized signal strength."""

        return SignalMeter(
            width=width,
            style="ascii",
        ).render(value)

    def history(self, values) -> str:
        """Render a Unicode sparkline for compatible output paths."""

        return Sparkline().render(values)

    def activity(self, frame: int) -> str:
        """Render one spinner frame."""

        return Spinner().render(frame)

    def performance_lines(
        self,
        cpu_percent: float,
        ram_percent: float,
    ) -> tuple[str, str]:
        """Render production-safe CPU and RAM dashboard lines."""

        cpu = max(0, min(100, round(float(cpu_percent))))
        ram = max(0, min(100, round(float(ram_percent))))

        cpu_line = (
            f"CPU {self.cpu(cpu, width=7)} {cpu}%"
        ).ljust(LCD_WIDTH)

        ram_line = (
            f"RAM {self.ram(ram, width=7)} {ram}%"
        ).ljust(LCD_WIDTH)

        return (
            cpu_line[:LCD_WIDTH],
            ram_line[:LCD_WIDTH],
        )


renderer = WidgetRenderer()
