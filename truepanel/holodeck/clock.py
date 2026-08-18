"""Deterministic clocks for repeatable whole-stack simulations."""

from __future__ import annotations

import math


def _finite_time(value: float, label: str) -> float:
    parsed = float(value)

    if not math.isfinite(parsed):
        raise ValueError(
            f"HoloDeck {label} must be finite"
        )

    return parsed


class DeterministicClock:
    """A wall/monotonic compatible clock advanced only by its owner."""

    def __init__(self, start: float = 0.0):
        self._start = _finite_time(
            start,
            "start time",
        )
        self._value = self._start

    def __call__(self) -> float:
        return self._value

    @property
    def value(self) -> float:
        return self._value

    def advance(self, seconds: float) -> float:
        seconds = _finite_time(
            seconds,
            "advance",
        )
        if seconds < 0:
            raise ValueError("HoloDeck time cannot move backwards")
        self._value += seconds
        return self._value

    def set(self, value: float) -> float:
        value = _finite_time(
            value,
            "set time",
        )
        if value < self._value:
            raise ValueError("HoloDeck time cannot move backwards")
        self._value = value
        return self._value

    def reset(self) -> float:
        """Return to the construction time for a fresh scenario run."""

        self._value = self._start
        return self._value
