"""Offline orchestration for TruePanel Black Box replay tooling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .black_box import BlackBoxFrame, BlackBoxRecorder, BlackBoxReplay
from .black_box_chaos import BlackBoxChaosScenario
from .black_box_compatibility import CompatibilityReplayProfile
from .black_box_narrator import BlackBoxIncident, BlackBoxIncidentNarrator
from .black_box_twin import BlackBoxDigitalTwin, DigitalTwinLCDState


@dataclass(frozen=True)
class BlackBoxReplayView:
    """One browser/support-safe view derived from an offline replay frame."""

    frame: BlackBoxFrame
    lcd: DigitalTwinLCDState
    incidents: tuple[BlackBoxIncident, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "frame": self.frame.as_dict(),
            "lcd": self.lcd.as_dict(),
            "incidents": [incident.as_dict() for incident in self.incidents],
        }


class BlackBoxReplaySession:
    """Compose replay, chaos, Digital Twin, and narration offline.

    A session owns an immutable source replay. An optional simulation-only chaos
    scenario is projected into a separate derived replay, and all downstream
    views are built from that same derived timeline. This keeps browser/support
    consumers from applying divergent interpretations of a recording.
    """

    def __init__(
        self,
        replay: BlackBoxReplay,
        *,
        chaos: BlackBoxChaosScenario | None = None,
        lcd_width: int = 16,
    ):
        if not isinstance(replay, BlackBoxReplay):
            raise TypeError("replay must be a BlackBoxReplay")
        if chaos is not None and not isinstance(chaos, BlackBoxChaosScenario):
            raise TypeError("chaos must be a BlackBoxChaosScenario or None")

        self.source_replay = replay
        self.chaos = chaos
        self.replay = BlackBoxReplay(
            chaos.apply(frame) if chaos is not None else frame
            for frame in replay.frames
        )
        self.twin = BlackBoxDigitalTwin(self.replay, width=lcd_width)
        self.narrator = BlackBoxIncidentNarrator(self.replay)
        self._incidents = self.narrator.incidents()
        self._incidents_by_sequence: dict[int, tuple[BlackBoxIncident, ...]] = {}
        for incident in self._incidents:
            existing = self._incidents_by_sequence.get(incident.sequence, ())
            self._incidents_by_sequence[incident.sequence] = existing + (incident,)

    @classmethod
    def from_recorder(
        cls,
        recorder: BlackBoxRecorder,
        *,
        chaos: BlackBoxChaosScenario | None = None,
        lcd_width: int = 16,
    ) -> BlackBoxReplaySession:
        if not isinstance(recorder, BlackBoxRecorder):
            raise TypeError("recorder must be a BlackBoxRecorder")
        return cls(recorder.load_replay(), chaos=chaos, lcd_width=lcd_width)

    @classmethod
    def from_compatibility_profile(
        cls,
        profile: CompatibilityReplayProfile,
        *,
        captured_at: float,
        sequence: int = 0,
        chaos: BlackBoxChaosScenario | None = None,
        lcd_width: int = 16,
    ) -> BlackBoxReplaySession:
        if not isinstance(profile, CompatibilityReplayProfile):
            raise TypeError("profile must be a CompatibilityReplayProfile")
        return cls(
            BlackBoxReplay((profile.to_black_box_frame(captured_at=captured_at, sequence=sequence),)),
            chaos=chaos,
            lcd_width=lcd_width,
        )

    @property
    def incidents(self) -> tuple[BlackBoxIncident, ...]:
        return self._incidents

    @property
    def simulation_only(self) -> bool:
        return self.chaos is not None

    def with_chaos(self, chaos: BlackBoxChaosScenario | None) -> BlackBoxReplaySession:
        """Return a new projection from the original recording.

        Replacing a scenario always starts from ``source_replay`` so simulated
        faults cannot accidentally stack across successive UI operations.
        """

        return type(self)(self.source_replay, chaos=chaos, lcd_width=self.twin.width)

    def at_sequence(self, sequence: int) -> BlackBoxReplayView | None:
        frame = self.replay.at_sequence(sequence)
        if frame is None:
            return None
        return self._view(frame)

    def at_or_before(self, captured_at: float) -> BlackBoxReplayView | None:
        frame = self.replay.at_or_before(captured_at)
        if frame is None:
            return None
        return self._view(frame)

    @property
    def timeline(self) -> tuple[BlackBoxReplayView, ...]:
        return tuple(self._view(frame) for frame in self.replay.frames)

    def _view(self, frame: BlackBoxFrame) -> BlackBoxReplayView:
        lcd = self.twin.at_sequence(frame.sequence)
        if lcd is None:
            raise RuntimeError("Digital Twin lost replay sequence")
        return BlackBoxReplayView(
            frame=frame,
            lcd=lcd,
            incidents=self._incidents_by_sequence.get(frame.sequence, ()),
        )


__all__ = ["BlackBoxReplaySession", "BlackBoxReplayView"]
