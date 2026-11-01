"""Short PC-speaker tones for Loadmaster, so the front panel need not be watched.

One tone per kind of moment, played when the service changes state:

========= ========================= ========================================
Tone      States                    Sound
========= ========================= ========================================
ready     READY                     two rising notes: work to do, press Copy
start     COPYING                   one blip: the Copy press was heard
done      DONE                      four-note "radio" chime: safe to remove
clear     CLEAR, EJECTED            one high chirp: up to date / unmounted
attention HOLD, CONFIRM, NEW_DRIVE  two falling notes: needs a decision
failed    PARTIAL, FAILED           three falling notes: look at the receipt
========= ========================= ========================================

Tones use the existing ``buzzer:`` section (they are silent when it is off)
and play on a background thread so the service never waits for them.
``loadmaster.sounds`` turns them off (``false``), sets ``quiet_hours``
("22:00-07:00") and overrides tones (``tones: {done: [[1047, 0.1], ...]}``).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any

LOGGER = logging.getLogger(__name__)

Notes = list[tuple[int, float]]

TONES: dict[str, Notes] = {
    "ready": [(784, 0.09), (1047, 0.12)],
    "start": [(1047, 0.06)],
    "done": [(1047, 0.10), (784, 0.09), (1175, 0.10), (988, 0.10)],
    "clear": [(1175, 0.08)],
    "attention": [(659, 0.15), (523, 0.25)],
    "failed": [(523, 0.20), (392, 0.20), (330, 0.40)],
}

STATE_TONES = {
    "READY": "ready",
    "COPYING": "start",
    "DONE": "done",
    "CLEAR": "clear",
    "EJECTED": "clear",
    "HOLD": "attention",
    "CONFIRM": "attention",
    "NEW_DRIVE": "attention",
    "PARTIAL": "failed",
    "FAILED": "failed",
}


class SoundsConfigError(ValueError):
    """The loadmaster.sounds section is invalid."""


def _minutes(text: str) -> int:
    hours, _, minutes = str(text).strip().partition(":")
    value = int(hours) * 60 + int(minutes or 0)
    if not 0 <= value < 24 * 60:
        raise ValueError(text)
    return value


def parse_sounds(value: Any) -> dict[str, Any]:
    """Normalise ``loadmaster.sounds`` (true / false / mapping)."""

    if value is None or value is True:
        return {"enabled": True, "quiet_hours": None, "tones": {}}
    if value is False:
        return {"enabled": False, "quiet_hours": None, "tones": {}}
    if not isinstance(value, dict):
        raise SoundsConfigError("loadmaster sounds must be true, false or a mapping")

    quiet = value.get("quiet_hours")
    if quiet:
        start, sep, end = str(quiet).partition("-")
        try:
            quiet = (_minutes(start), _minutes(end)) if sep else None
        except ValueError as error:
            raise SoundsConfigError(
                f"loadmaster sounds quiet_hours is invalid: {quiet}"
            ) from error
        if quiet is None:
            raise SoundsConfigError(
                "loadmaster sounds quiet_hours must look like 22:00-07:00"
            )

    tones = {}
    for name, notes in (value.get("tones") or {}).items():
        if name not in TONES:
            raise SoundsConfigError(f"unknown Loadmaster tone: {name}")
        try:
            tones[name] = [(int(f), float(d)) for f, d in notes]
        except (TypeError, ValueError) as error:
            raise SoundsConfigError(
                f"tone {name} must be [[frequency, seconds], ...]"
            ) from error
        if not tones[name] or any(
            not 0 <= f <= 20000 or not 0 < d <= 2 for f, d in tones[name]
        ):
            raise SoundsConfigError(f"tone {name} has a note out of range")
    return {
        "enabled": value.get("enabled", True) is not False,
        "quiet_hours": quiet,
        "tones": tones,
    }


class Sounds:
    """Plays a tone for a state change, off the caller's thread."""

    def __init__(
        self,
        sounds: dict[str, Any],
        player: Any,
        *,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.enabled = bool(sounds.get("enabled")) and bool(
            getattr(player, "enabled", False)
        )
        self.quiet_hours = sounds.get("quiet_hours")
        self.tones = {**TONES, **(sounds.get("tones") or {})}
        self.player = player
        self.now = now

    def quiet(self) -> bool:
        if not self.quiet_hours:
            return False
        start, end = self.quiet_hours
        clock = self.now()
        minute = clock.hour * 60 + clock.minute
        return (
            start <= minute < end if start <= end else minute >= start or minute < end
        )

    def for_state(self, state: str) -> None:
        name = STATE_TONES.get(state)
        if name:
            self.play(name)

    def play(self, name: str, *, wait: bool = False) -> bool:
        if not self.enabled or self.quiet():
            return False
        notes = self.tones[name]
        if wait:
            return self._melody(notes)
        threading.Thread(
            target=self._melody, args=(notes,), name="loadmaster-sound", daemon=True
        ).start()
        return True

    def _melody(self, notes: Notes) -> bool:
        try:
            return bool(self.player.melody(notes))
        except Exception:  # noqa: BLE001 - a missing speaker must never stop a sync
            LOGGER.exception("Loadmaster tone failed")
            return False


def build_sounds(config: dict[str, Any], sounds: dict[str, Any]) -> Sounds:
    from truepanel.hardware.buzzer import Buzzer

    return Sounds(sounds, Buzzer(config.get("buzzer", {})))


__all__ = [
    "STATE_TONES",
    "TONES",
    "Sounds",
    "SoundsConfigError",
    "build_sounds",
    "parse_sounds",
]
