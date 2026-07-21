"""
Safe startup animation for verified TVS-671 bay LEDs.

The animation coordinates the verified red identify and green presence
channels. Red identify LEDs are always cleared afterward, and green presence
LEDs are restored so normal drive indication can resume.
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
    "step_delay": 1.0,
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
    Perform a red-to-green bay LED startup sequence.

    Individual hardware failures are logged and skipped. Cleanup restores the
    verified green presence LEDs and clears red identify LEDs regardless of
    where the animation fails.
    """

    def __init__(
        self,
        controller,
        *,
        step_delay: float = 1.0,
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

    def _set_error(
        self,
        bay: int,
        enabled: bool,
    ) -> bool:
        try:
            return bool(
                self.controller.set_error(
                    bay,
                    enabled,
                    force=True,
                )
            )
        except Exception:
            LOGGER.exception(
                "Startup LED animation could not set "
                "Bay %d error LED %s",
                bay,
                "ON" if enabled else "OFF",
            )
            return False

    def _set_present(
        self,
        bay: int,
        enabled: bool,
    ) -> bool:
        try:
            return bool(
                self.controller.set_present(
                    bay,
                    enabled,
                    force=True,
                )
            )
        except Exception:
            LOGGER.exception(
                "Startup LED animation could not set "
                "Bay %d presence LED %s",
                bay,
                "ON" if enabled else "OFF",
            )
            return False

    def _delay(self, seconds: float) -> None:
        if seconds > 0:
            self.sleeper(seconds)

    def _clear_red(self) -> None:
        for bay in range(1, 7):
            self._set_error(
                bay,
                False,
            )

    def _restore_green(self) -> None:
        for bay in range(1, 7):
            self._set_present(
                bay,
                True,
            )

    def run(self) -> None:
        """Run the complete startup sequence and restore normal LED state."""

        LOGGER.info(
            "Starting TVS-671 red-to-green bay LED animation"
        )

        try:
            # Hide native green presence LEDs before the visible sequence.
            for bay in range(1, 7):
                self._set_present(
                    bay,
                    False,
                )

            # Illuminate steady red error LEDs from Bay 1 through Bay 6.
            for bay in range(1, 7):
                self._set_error(
                    bay,
                    True,
                )
                self._delay(
                    self.step_delay
                )

            # Clear steady red error LEDs from Bay 6 back through Bay 1.
            for bay in range(6, 0, -1):
                self._set_error(
                    bay,
                    False,
                )
                self._delay(
                    self.step_delay
                )

            # Reveal green presence LEDs from Bay 1 through Bay 6.
            for bay in range(1, 7):
                self._set_present(
                    bay,
                    True,
                )
                self._delay(
                    self.step_delay
                )

            self._delay(
                self.pulse_hold
            )
        finally:
            # Always clear steady red and restore normal green state.
            self._clear_red()
            self._restore_green()

            if self.clear_when_finished:
                try:
                    self.controller.clear_all()
                except Exception:
                    LOGGER.exception(
                        "Startup LED animation could not clear "
                        "all identify LEDs"
                    )

        LOGGER.info(
            "TVS-671 red-to-green bay LED animation complete"
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
            1.0,
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
