"""
Reusable Flight Deck instruments for the TruePanel 16x2 LCD.

The instrument layer provides a consistent visual vocabulary above the
low-level A125 native renderer. Instruments render exact-width byte rows and
may be composed into a NativeInstrumentFrame by InstrumentPage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from truepanel.display.native_renderer import (
    LCD_WIDTH,
    NativeInstrumentFrame,
    NativeInstrumentRenderer,
    clamp_percentage,
    fit_text,
)


def _required_label(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("instrument label is required")

    return value.strip().upper()


def _ascii_text(value, width=LCD_WIDTH) -> bytes:
    return str(value).encode(
        "ascii",
        errors="replace",
    )[:width].ljust(width, b" ")


class Instrument:
    """Base interface implemented by all single-row instruments."""

    def render_line(self) -> bytes:
        raise NotImplementedError


@dataclass(frozen=True)
class InstrumentGauge(Instrument):
    """Percentage gauge rendered with the native A125 block-cell bar."""

    label: str
    value: float
    width: int = 6
    renderer: NativeInstrumentRenderer = field(
        default_factory=NativeInstrumentRenderer,
        compare=False,
        repr=False,
    )

    def __post_init__(self):
        _required_label(self.label)

        if self.width <= 0:
            raise ValueError("gauge width must be greater than zero")

    def render_line(self) -> bytes:
        return self.renderer.gauge_line(
            self.label,
            self.value,
            width=self.width,
        )


@dataclass(frozen=True)
class InstrumentProgress(Instrument):
    """
    Operation progress instrument.

    Progress currently shares the native gauge representation but exists as a
    separate semantic type so animations and operation-specific presentation
    can evolve independently.
    """

    label: str
    percent: float
    width: int = 6
    renderer: NativeInstrumentRenderer = field(
        default_factory=NativeInstrumentRenderer,
        compare=False,
        repr=False,
    )

    def __post_init__(self):
        _required_label(self.label)

        if self.width <= 0:
            raise ValueError("progress width must be greater than zero")

    def render_line(self) -> bytes:
        return self.renderer.gauge_line(
            self.label,
            self.percent,
            width=self.width,
        )


@dataclass(frozen=True)
class InstrumentStatus(Instrument):
    """Compact label/value status row."""

    label: str
    value: str
    separator: str = " "

    def __post_init__(self):
        _required_label(self.label)

        if self.value is None or not str(self.value).strip():
            raise ValueError("status value is required")

    def render_line(self) -> bytes:
        label = _required_label(self.label)[:6]
        value = str(self.value).strip().upper()

        available = LCD_WIDTH - len(label) - len(self.separator)

        if available <= 0:
            raise ValueError("status label does not fit")

        line = (
            label
            + self.separator
            + value[:available].rjust(available)
        )

        return _ascii_text(line)


@dataclass(frozen=True)
class InstrumentTrend(Instrument):
    """
    Compact history instrument rendered by NativeInstrumentRenderer.

    The instrument owns semantic inputs while the native renderer owns all
    normalization, density selection, row formatting, and byte-width rules.
    """

    label: str
    values: Iterable[float]
    width: int = 7
    renderer: NativeInstrumentRenderer = field(
        default_factory=NativeInstrumentRenderer,
        compare=False,
        repr=False,
    )

    LEVELS = NativeInstrumentRenderer.TREND_LEVELS

    def __post_init__(self):
        _required_label(
            self.label
        )

        if self.width <= 0:
            raise ValueError(
                "trend width must be greater than zero"
            )

        if self.width > 8:
            raise ValueError(
                "trend width cannot exceed eight cells"
            )

        object.__setattr__(
            self,
            "values",
            tuple(self.values),
        )

    def normalized_values(self) -> list[float]:
        """
        Retain the existing public helper while delegating its implementation
        to the native renderer.
        """

        normalizer = getattr(
            self.renderer,
            "normalize_trend_values",
            None,
        )

        if normalizer is None:
            normalizer = (
                NativeInstrumentRenderer()
                .normalize_trend_values
            )

        return normalizer(
            self.values,
            width=self.width,
        )

    def render_line(self) -> bytes:
        # Preserve the simple trend_line(label, values) renderer contract for
        # the standard width. This also keeps lightweight test renderers easy
        # to implement.
        if self.width == 7:
            return self.renderer.trend_line(
                self.label,
                self.values,
            )

        return self.renderer.trend_line(
            self.label,
            self.values,
            width=self.width,
        )


@dataclass
class InstrumentPage:
    """
    Compose instruments into an exact-width two-row LCD frame.

    Layout rules:

    * No instruments: title on row one, blank row two.
    * One instrument: title on row one, instrument on row two.
    * Two instruments: one instrument per row.
    * More than two instruments: rejected because the physical display has
      only two rows.
    """

    title: str
    instruments: list[Instrument] = field(
        default_factory=list,
    )

    def __post_init__(self):
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("page title is required")

    def add(self, instrument: Instrument):
        if not isinstance(instrument, Instrument):
            raise TypeError(
                "page items must be Instrument instances"
            )

        if len(self.instruments) >= 2:
            raise ValueError(
                "a 16x2 instrument page supports at most two instruments"
            )

        self.instruments.append(instrument)
        return self

    def render(self) -> NativeInstrumentFrame:
        if not self.instruments:
            return NativeInstrumentFrame(
                fit_text(self.title),
                fit_text(""),
            )

        if len(self.instruments) == 1:
            return NativeInstrumentFrame(
                fit_text(self.title),
                self.instruments[0].render_line(),
            )

        return NativeInstrumentFrame(
            self.instruments[0].render_line(),
            self.instruments[1].render_line(),
        )
