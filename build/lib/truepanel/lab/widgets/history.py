"""
Fixed-size history buffer for LCD widgets.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class HistoryBuffer:
    """Store the most recent numeric samples."""

    size: int = 16
    initial: Iterable[float] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.size < 1:
            raise ValueError(
                "size must be at least 1"
            )

        self._values = deque(
            maxlen=self.size,
        )

        self.extend(self.initial)

    def append(
        self,
        value: float,
    ) -> None:
        self._values.append(
            float(value)
        )

    def extend(
        self,
        values: Iterable[float],
    ) -> None:
        for value in values:
            self.append(value)

    def clear(self) -> None:
        self._values.clear()

    def values(self) -> tuple[float, ...]:
        return tuple(self._values)

    @property
    def latest(self) -> float | None:
        if not self._values:
            return None

        return self._values[-1]

    @property
    def full(self) -> bool:
        return len(self._values) == self.size

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self):
        return iter(self._values)
