"""Time-bounded physical bay identification for Project Lifeline.

This service controls only the verified identify LED channel. It cannot change
storage state, pool membership, filesystem state, or arbitrary enclosure LEDs.
"""

from __future__ import annotations

import logging
import threading
from typing import Any


LOGGER = logging.getLogger(__name__)
DEFAULT_IDENTIFY_SECONDS = 15.0
MAX_IDENTIFY_SECONDS = 60.0


class BayIdentificationService:
    """Flash one verified bay identify LED and automatically clear it."""

    def __init__(
        self,
        *,
        controller=None,
        default_seconds: float = DEFAULT_IDENTIFY_SECONDS,
        timer_factory=None,
    ) -> None:
        self._controller = controller
        self.default_seconds = max(
            1.0,
            min(float(default_seconds), MAX_IDENTIFY_SECONDS),
        )
        self._timer_factory = timer_factory or threading.Timer
        self._lock = threading.RLock()
        self._timers: dict[int, Any] = {}

    def _controller_service(self):
        if self._controller is not None:
            return self._controller
        from truepanel.hardware.manager import HardwareManager

        self._controller = HardwareManager().bay_leds
        return self._controller

    def identify(self, bay: int, *, seconds: float | None = None) -> dict[str, Any]:
        duration = self.default_seconds if seconds is None else float(seconds)
        duration = max(1.0, min(duration, MAX_IDENTIFY_SECONDS))
        controller = self._controller_service()
        bay = controller.validate_bay(bay)

        with self._lock:
            previous = self._timers.pop(bay, None)
            if previous is not None:
                previous.cancel()

            controller.set_identify(bay, True, force=True)
            timer = self._timer_factory(duration, self._clear, args=(bay,))
            timer.daemon = True
            self._timers[bay] = timer
            timer.start()

        return {
            "bay": bay,
            "identify": True,
            "duration_seconds": duration,
            "storage_mutation": False,
            "hardware_action": "identify_led",
        }

    def _clear(self, bay: int) -> None:
        try:
            controller = self._controller_service()
            controller.set_identify(bay, False, force=True)
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            LOGGER.warning(
                "Unable to clear Lifeline identify LED for Bay %s: %s",
                bay,
                error,
            )
        finally:
            with self._lock:
                self._timers.pop(int(bay), None)

    def clear(self, bay: int) -> dict[str, Any]:
        controller = self._controller_service()
        bay = controller.validate_bay(bay)
        with self._lock:
            timer = self._timers.pop(bay, None)
            if timer is not None:
                timer.cancel()
            controller.set_identify(bay, False, force=True)
        return {
            "bay": bay,
            "identify": False,
            "storage_mutation": False,
            "hardware_action": "identify_led",
        }


__all__ = [
    "BayIdentificationService",
    "DEFAULT_IDENTIFY_SECONDS",
    "MAX_IDENTIFY_SECONDS",
]
