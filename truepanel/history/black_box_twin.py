"""Read-only Digital Twin projections for TruePanel Black Box recordings."""

from __future__ import annotations

from dataclasses import dataclass

from truepanel.history.black_box import BlackBoxFrame, BlackBoxReplay

DEFAULT_LCD_WIDTH = 16


def _lcd_text(value: object, *, width: int) -> str:
    """Return deterministic fixed-width LCD text for replay rendering."""

    text = "" if value is None else str(value)
    return text[:width].ljust(width)


@dataclass(frozen=True)
class DigitalTwinLCDState:
    """One renderable, immutable LCD state projected from a Black Box frame."""

    sequence: int
    captured_at: float
    page: str
    line1: str
    line2: str
    source: str
    stale: bool
    available: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "captured_at": self.captured_at,
            "page": self.page,
            "line1": self.line1,
            "line2": self.line2,
            "source": self.source,
            "stale": self.stale,
            "available": self.available,
        }


def project_lcd_state(
    frame: BlackBoxFrame,
    *,
    width: int = DEFAULT_LCD_WIDTH,
) -> DigitalTwinLCDState:
    """Project a sanitized Black Box frame into browser-safe LCD state.

    The projection is deliberately data-only. It never opens serial devices,
    invokes display commands, or consults live runtime providers.
    """

    if not isinstance(frame, BlackBoxFrame):
        raise TypeError("frame must be a BlackBoxFrame")

    lcd_width = int(width)
    if lcd_width < 1 or lcd_width > 256:
        raise ValueError("LCD projection width must be between 1 and 256")

    lcd = frame.lcd
    available = bool(lcd.get("available", bool(lcd)))

    return DigitalTwinLCDState(
        sequence=frame.sequence,
        captured_at=frame.captured_at,
        page=str(lcd.get("page", "unavailable")),
        line1=_lcd_text(lcd.get("line1"), width=lcd_width),
        line2=_lcd_text(lcd.get("line2"), width=lcd_width),
        source=str(lcd.get("source", "black-box")),
        stale=bool(lcd.get("stale", False)),
        available=available,
    )


class BlackBoxDigitalTwin:
    """Deterministic LCD view over an immutable Black Box replay."""

    def __init__(
        self,
        replay: BlackBoxReplay,
        *,
        width: int = DEFAULT_LCD_WIDTH,
    ):
        if not isinstance(replay, BlackBoxReplay):
            raise TypeError("replay must be a BlackBoxReplay")

        lcd_width = int(width)
        if lcd_width < 1 or lcd_width > 256:
            raise ValueError("LCD projection width must be between 1 and 256")

        self.replay = replay
        self.width = lcd_width

    def project(self, frame: BlackBoxFrame) -> DigitalTwinLCDState:
        return project_lcd_state(frame, width=self.width)

    @property
    def timeline(self) -> tuple[DigitalTwinLCDState, ...]:
        return tuple(self.project(frame) for frame in self.replay.frames)

    def at_sequence(self, sequence: int) -> DigitalTwinLCDState | None:
        frame = self.replay.at_sequence(sequence)
        if frame is None:
            return None
        return self.project(frame)

    def at_or_before(
        self,
        captured_at: float,
    ) -> DigitalTwinLCDState | None:
        frame = self.replay.at_or_before(captured_at)
        if frame is None:
            return None
        return self.project(frame)

    def between(
        self,
        start_at: float,
        end_at: float,
    ) -> tuple[DigitalTwinLCDState, ...]:
        return tuple(
            self.project(frame)
            for frame in self.replay.between(start_at, end_at)
        )
