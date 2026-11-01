"""
Native A125 instrument rendering.

This module renders compact two-line dashboard instruments using only
hardware-supported character bytes:

    0x20  blank cell
    0xFF  full block

No CGRAM or user-defined glyph support is assumed.
"""

from __future__ import annotations

from dataclasses import dataclass


LCD_WIDTH = 16
EMPTY_CELL = 0x20
FULL_CELL = 0xFF


def clamp_percentage(value) -> int:
    """Normalize any percentage-like value to an integer from 0 through 100."""

    try:
        value = round(float(value))
    except (TypeError, ValueError):
        value = 0

    return max(0, min(100, value))


def fit_text(value, width=LCD_WIDTH) -> bytes:
    """Encode and fit one LCD row using the A125-compatible Latin-1 path."""

    text = str(value).encode(
        "latin-1",
        errors="replace",
    )

    return text[:width].ljust(
        width,
        bytes((EMPTY_CELL,)),
    )


@dataclass(frozen=True)
class NativeInstrumentFrame:
    """Two exact-width LCD rows."""

    line1: bytes
    line2: bytes

    def __post_init__(self):
        line1 = bytes(self.line1)
        line2 = bytes(self.line2)

        if len(line1) != LCD_WIDTH:
            raise ValueError(
                "line1 must be exactly 16 bytes"
            )

        if len(line2) != LCD_WIDTH:
            raise ValueError(
                "line2 must be exactly 16 bytes"
            )

        object.__setattr__(
            self,
            "line1",
            line1,
        )
        object.__setattr__(
            self,
            "line2",
            line2,
        )

    @property
    def lines(self):
        return self.line1, self.line2

    def as_dict(self):
        return {
            "line1": list(self.line1),
            "line2": list(self.line2),
            "line1_hex": self.line1.hex(" ").upper(),
            "line2_hex": self.line2.hex(" ").upper(),
        }


class NativeInstrumentRenderer:
    """
    Render production Flight Deck instruments.

    raw_blocks=True selects the confirmed A125 full-block byte. False returns
    an ASCII-compatible representation useful for terminals and fallback
    backends.
    """

    TREND_LEVELS = " .:-=+*#"

    def __init__(
        self,
        *,
        raw_blocks=True,
        full_cell=FULL_CELL,
        empty_cell=EMPTY_CELL,
    ):
        self.raw_blocks = bool(
            raw_blocks
        )
        self.full_cell = int(
            full_cell
        )
        self.empty_cell = int(
            empty_cell
        )

        for name, value in (
            ("full_cell", self.full_cell),
            ("empty_cell", self.empty_cell),
        ):
            if not 0 <= value <= 0xFF:
                raise ValueError(
                    f"{name} must fit in one byte"
                )

    def bar(
        self,
        percent,
        *,
        width,
    ) -> bytes:
        """
        Render a deterministic whole-cell progress bar.

        Filled cells use round-half-up behavior through integer arithmetic.
        """

        if width <= 0:
            raise ValueError(
                "width must be greater than zero"
            )

        value = clamp_percentage(
            percent
        )

        filled = min(
            width,
            (value * width + 50) // 100,
        )

        if self.raw_blocks:
            full = bytes(
                (self.full_cell,)
            )
            empty = bytes(
                (self.empty_cell,)
            )
        else:
            full = b"#"
            empty = b"-"

        return (
            full * filled
            + empty * (width - filled)
        )

    def gauge_line(
        self,
        label,
        percent,
        *,
        width=6,
    ) -> bytes:
        """Render LABEL, six-cell bar, and percentage in one 16-byte row."""

        if not isinstance(
            label,
            str,
        ) or not label.strip():
            raise ValueError(
                "label is required"
            )

        value = clamp_percentage(
            percent
        )

        prefix = (
            f"{label.strip().upper()[:3]:<3} "
        ).encode("ascii")

        suffix = (
            f" {value:>3}%"
        ).encode("ascii")

        available = (
            LCD_WIDTH
            - len(prefix)
            - len(suffix)
        )

        bar_width = min(
            int(width),
            available,
        )

        if bar_width <= 0:
            raise ValueError(
                "gauge width does not fit"
            )

        line = (
            prefix
            + self.bar(
                value,
                width=bar_width,
            )
            + suffix
        )

        return line[:LCD_WIDTH].ljust(
            LCD_WIDTH,
            bytes((self.empty_cell,)),
        )

    def normalize_trend_values(
        self,
        values,
        *,
        width=7,
    ) -> list[float]:
        """
        Normalize trend history into a fixed-width sequence.

        Values from zero through one are treated as ratios. Larger values are
        scaled relative to the largest visible sample. Missing leading samples
        are represented by empty cells.
        """

        width = int(width)

        if width <= 0:
            raise ValueError(
                "trend width must be greater than zero"
            )

        if width > 8:
            raise ValueError(
                "trend width cannot exceed eight cells"
            )

        def numeric(value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        samples = [
            max(
                0.0,
                numeric(value),
            )
            for value in tuple(values)
        ]

        samples = samples[-width:]

        if not samples:
            return [0.0] * width

        maximum = max(samples)

        if maximum <= 0:
            normalized = [
                0.0
                for _ in samples
            ]
        elif maximum <= 1.0:
            normalized = [
                min(
                    1.0,
                    value,
                )
                for value in samples
            ]
        else:
            normalized = [
                value / maximum
                for value in samples
            ]

        return (
            [0.0] * (
                width - len(normalized)
            )
            + normalized
        )

    def trend_line(
        self,
        label,
        values,
        *,
        width=7,
    ) -> bytes:
        """
        Render a compact ASCII sparkline and current normalized percentage.

        Safe ASCII density characters are used because the A125 laboratory has
        confirmed a native full block but not programmable partial-height
        glyphs.
        """

        if not isinstance(
            label,
            str,
        ) or not label.strip():
            raise ValueError(
                "label is required"
            )

        normalized = self.normalize_trend_values(
            values,
            width=width,
        )

        sparkline = "".join(
            self.TREND_LEVELS[
                min(
                    len(self.TREND_LEVELS) - 1,
                    round(
                        value
                        * (
                            len(self.TREND_LEVELS)
                            - 1
                        )
                    ),
                )
            ]
            for value in normalized
        )

        current = clamp_percentage(
            normalized[-1] * 100
        )

        prefix = (
            f"{label.strip().upper()[:3]:<3} "
        )

        line = (
            f"{prefix}"
            f"{sparkline}"
            f" {current:>3}%"
        )

        return fit_text(
            line
        )

    def performance(
        self,
        cpu_percent,
        ram_percent,
    ) -> NativeInstrumentFrame:
        return NativeInstrumentFrame(
            self.gauge_line(
                "CPU",
                cpu_percent,
            ),
            self.gauge_line(
                "RAM",
                ram_percent,
            ),
        )

    def thermal(
        self,
        drive,
        degrees,
        *,
        minimum=20,
        maximum=80,
    ) -> NativeInstrumentFrame:
        if maximum <= minimum:
            raise ValueError(
                "maximum must be greater than minimum"
            )

        try:
            temperature = float(
                degrees
            )
        except (TypeError, ValueError):
            temperature = float(
                minimum
            )

        ratio = (
            temperature - minimum
        ) / (
            maximum - minimum
        )

        percent = clamp_percentage(
            ratio * 100
        )

        display_temp = round(
            temperature
        )

        title = (
            f"TEMP {str(drive)[:5]:<5} "
            f"{display_temp:>2}C"
        )

        return NativeInstrumentFrame(
            fit_text(title),
            self.gauge_line(
                "TMP",
                percent,
            ),
        )

    def capacity(
        self,
        pool,
        percent,
    ) -> NativeInstrumentFrame:
        value = clamp_percentage(
            percent
        )

        title = (
            f"POOL {str(pool)[:6]:<6} "
            f"{value:>3}%"
        )

        return NativeInstrumentFrame(
            fit_text(title),
            self.gauge_line(
                "USE",
                value,
            ),
        )

    def mission(
        self,
        *,
        ready=True,
        health_percent=100,
    ) -> NativeInstrumentFrame:
        title = (
            " MISSION READY  "
            if ready
            else " MISSION ALERT  "
        )

        return NativeInstrumentFrame(
            fit_text(title),
            self.gauge_line(
                "SYS",
                health_percent,
            ),
        )
