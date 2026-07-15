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

    def thermal_bar_line(
        self,
        degrees: float,
        *,
        minimum: float = 20,
        maximum: float = 80,
        width: int = 6,
        style: str = "ascii",
    ) -> str:
        """
        Render one compact temperature gauge.

        The percentage represents the temperature's position within the
        configured operating range.
        """

        if maximum <= minimum:
            raise ValueError(
                "maximum must be greater than minimum"
            )

        if width <= 0:
            raise ValueError(
                "width must be greater than zero"
            )

        try:
            value = float(degrees)
        except (TypeError, ValueError):
            value = minimum

        ratio = (
            (value - minimum)
            / (maximum - minimum)
        )

        percent = self._percentage(
            ratio * 100
        )

        bar = ProgressBar(
            width=width,
            style=style,
        ).render_percent(percent)

        line = (
            f"TMP "
            f"{bar} "
            f"{percent:>3}%"
        )

        return line[:LCD_WIDTH].ljust(LCD_WIDTH)

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

    def history_line(
        self,
        label: str,
        values,
        *,
        width: int = 12,
        style: str = "ascii",
    ) -> str:
        """
        Render a labeled history sparkline across one LCD row.

        ASCII is the production default because the A125 character display
        cannot reliably render Unicode block glyphs. Unicode remains available
        for terminal previews and compatible display backends.
        """

        if not isinstance(label, str) or not label.strip():
            raise ValueError("label is required")

        if width <= 0:
            raise ValueError(
                "width must be greater than zero"
            )

        if style not in {"ascii", "unicode"}:
            raise ValueError(
                "style must be ascii or unicode"
            )

        samples = list(values or ())[-width:]

        if len(samples) < width:
            samples = (
                [0.0] * (width - len(samples))
                + samples
            )

        sparkline = Sparkline(
            width=width,
        ).render(samples)

        if style == "ascii":
            sparkline = sparkline.translate(
                str.maketrans(
                    {
                        "▁": ".",
                        "▂": ":",
                        "▃": "-",
                        "▄": "=",
                        "▅": "+",
                        "▆": "*",
                        "▇": "#",
                        "█": "@",
                    }
                )
            )

        line = (
            f"{label.strip().upper()[:3]:<3} "
            f"{sparkline}"
        )

        return line[:LCD_WIDTH].ljust(LCD_WIDTH)

    @staticmethod
    def _percentage(value: float) -> int:
        try:
            value = round(float(value))
        except (TypeError, ValueError):
            value = 0

        return max(0, min(100, value))

    def performance_bar_line(
        self,
        label: str,
        percent: float,
        *,
        width: int = 6,
        style: str = "ascii",
    ) -> str:
        """
        Render one compact performance row.

        A six-cell bar leaves enough room for a three-character label and a
        right-aligned percentage on a 16-character LCD.
        """

        if not isinstance(label, str) or not label.strip():
            raise ValueError("label is required")

        if width <= 0:
            raise ValueError(
                "width must be greater than zero"
            )

        value = self._percentage(percent)

        bar = ProgressBar(
            width=width,
            style=style,
        ).render_percent(value)

        line = (
            f"{label.strip().upper()[:3]:<3} "
            f"{bar} "
            f"{value:>3}%"
        )

        return line[:LCD_WIDTH].ljust(LCD_WIDTH)

    def performance_bar_lines(
        self,
        cpu_percent: float,
        ram_percent: float,
        *,
        width: int = 6,
        style: str = "ascii",
    ) -> tuple[str, str]:
        """
        Render graphical CPU and RAM rows for the Flight Deck.
        """

        return (
            self.performance_bar_line(
                "CPU",
                cpu_percent,
                width=width,
                style=style,
            ),
            self.performance_bar_line(
                "RAM",
                ram_percent,
                width=width,
                style=style,
            ),
        )

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
