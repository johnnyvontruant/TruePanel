"""Deterministic clocks for repeatable whole-stack simulations."""

from __future__ import annotations


class DeterministicClock:
    """A wall/monotonic compatible clock advanced only by its owner."""

    def __init__(self, start: float = 0.0):
        self._start = float(start)
        self._value = self._start

    def __call__(self) -> float:
        return self._value

    @property
    def value(self) -> float:
        return self._value

    def advance(self, seconds: float) -> float:
        seconds = float(seconds)
        if seconds < 0:
            raise ValueError("HoloDeck time cannot move backwards")
        self._value += seconds
        return self._value

    def set(self, value: float) -> float:
        value = float(value)
        if value < self._value:
            raise ValueError("HoloDeck time cannot move backwards")
        self._value = value
        return self._value

    def reset(self) -> float:
        """Return to the construction time for a fresh scenario run."""

        self._value = self._start
        return self._value
