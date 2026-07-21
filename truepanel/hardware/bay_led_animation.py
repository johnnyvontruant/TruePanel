"""
Safe startup animation for verified TVS-671 bay identify LEDs.

Only the known red identify channel is controlled. The animation always clears
the identify LEDs when finished so native drive activity and status lighting
can resume.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from typing import Any

from .bay_leds import TVS671BayLedController


LOGGER = logging.getLogger(__name__)

DEFAULT_BAY_LED_ANIMATION_CONFIG = {
    "enabled": False,
    "step_delay": 0.12,
    "pulse_hold": 0.35,
    "clear_when_finished": True,
}


def get_bay_led_animation_config(
    config: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return startup bay-LED animation settings merged with defaults."""

    settings = dict(
        DEFAULT_BAY_LED_ANIMATION_CONFIG
    )

    if not isinstance(config, Mapping):
        return settings

    flightdeck = config.get(
        "flightdeck",
        {},
    )

    if not isinstance(
        flightdeck,
        Mapping,
    ):
        return settings

    startup = flightdeck.get(
        "startup",
        {},
    )

    if not isinstance(
        startup,
        Mapping,
    ):
        return settings

    overrides = startup.get(
        "bay_led_animation",
        {},
    )

    if isinstance(overrides, Mapping):
        settings.update(overrides)

    return settings


class BayLedStartupAnimation:
    """
    Perform a short red identify-LED preflight sequence.

    Individual hardware failures are logged and skipped. Cleanup is attempted
    regardless of where the animation fails.
    """

    def __init__(
        self,
        controller,
        *,
        step_delay: float = 0.12,
        pulse_hold: float = 0.35,
        clear_when_finished: bool = True,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.controller = controller
        self.step_delay = max(
            0.0,
            float(step_delay),
        )
        self.pulse_hold = max(
            0.0,
            float(pulse_hold),
        )
        self.clear_when_finished = bool(
            clear_when_finished
        )
        self.sleeper = sleeper

    def _set(
        self,
        bay: int,
        enabled: bool,
    ) -> bool:
        try:
            return bool(
                self.controller.set_identify(
                    bay,
                    enabled,
                    force=True,
                )
            )
        except Exception:
            LOGGER.exception(
                "Startup LED animation could not set Bay %d %s",
                bay,
                "ON" if enabled else "OFF",
            )
            return False

    def _delay(self, seconds: float) -> None:
        if seconds > 0:
            self.sleeper(seconds)

    def run(self) -> None:
        """Run the complete startup sequence and restore normal LED state."""

        LOGGER.info(
            "Starting TVS-671 bay LED preflight animation"
        )

        try:
            for bay in range(1, 7):
                self._set(
                    bay,
                    True,
                )
                self._delay(
                    self.step_delay
                )

            for bay in range(6, 0, -1):
                self._set(
                    bay,
                    False,
                )
                self._delay(
                    self.step_delay
                )

            for bay in range(1, 7):
                self._set(
                    bay,
                    True,
                )

            self._delay(
                self.pulse_hold
            )
        finally:
            if self.clear_when_finished:
                try:
                    self.controller.clear_all()
                except Exception:
                    LOGGER.exception(
                        "Startup LED animation could not clear all bays"
                    )

        LOGGER.info(
            "TVS-671 bay LED preflight animation complete"
        )


def build_bay_led_startup_animation(
    config: Mapping[str, Any] | None,
    *,
    controller=None,
    sleeper: Callable[[float], None] = time.sleep,
) -> BayLedStartupAnimation | None:
    """Construct the configured animation, or return None when disabled."""

    settings = get_bay_led_animation_config(
        config
    )

    if not bool(
        settings.get(
            "enabled",
            False,
        )
    ):
        return None

    if controller is None:
        hardware = (
            config.get("hardware", {})
            if isinstance(config, Mapping)
            else {}
        )

        bay_led_config = (
            hardware.get("bay_leds", {})
            if isinstance(hardware, Mapping)
            else {}
        )

        controller = TVS671BayLedController(
            bay_led_config
        )

    return BayLedStartupAnimation(
        controller,
        step_delay=settings.get(
            "step_delay",
            0.12,
        ),
        pulse_hold=settings.get(
            "pulse_hold",
            0.35,
        ),
        clear_when_finished=settings.get(
            "clear_when_finished",
            True,
        ),
        sleeper=sleeper,
    )


__all__ = [
    "BayLedStartupAnimation",
    "DEFAULT_BAY_LED_ANIMATION_CONFIG",
    "build_bay_led_startup_animation",
    "get_bay_led_animation_config",
]
