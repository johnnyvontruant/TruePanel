"""
Cooldown tracking for laboratory execution.

The cooldown tracker contains no hardware logic. It records successful
execution times and determines whether another request may proceed.
"""

import time


class CooldownTracker:
    def __init__(self, cooldown_seconds=1.0, clock=None):
        if cooldown_seconds < 0:
            raise ValueError(
                "cooldown_seconds cannot be negative"
            )

        self.cooldown_seconds = float(cooldown_seconds)
        self.clock = clock or time.monotonic
        self._last_execution = {}

    def remaining(self, key):
        if key not in self._last_execution:
            return 0.0

        elapsed = self.clock() - self._last_execution[key]

        return max(
            0.0,
            self.cooldown_seconds - elapsed,
        )

    def ready(self, key):
        return self.remaining(key) <= 0.0

    def record(self, key):
        self._last_execution[key] = self.clock()

    def clear(self, key=None):
        if key is None:
            self._last_execution.clear()
            return

        self._last_execution.pop(key, None)
