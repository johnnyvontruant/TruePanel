"""
Translate structured storage-health events into physical bay LED state.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Mapping
from typing import Any

from .constants import Category

LOGGER = logging.getLogger(__name__)


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class StorageBayIndicator:
    """
    Maintain verified warning/fault LED semantics for unhealthy physical bays.

    Warning storage health uses the flashing red identify channel. Critical
    storage health uses the steady red error channel. Recovery clears both red
    channels. The independent green presence channel is never modified here.

    Hardware failures are logged and deliberately do not interrupt Mission
    Control, LCD rendering, or storage-health polling.
    """

    def __init__(
        self,
        controller,
        *,
        clear_on_start: bool = False,
        temperature_led_on_c: int = 48,
        temperature_led_off_c: int = 45,
        temperature_led_immediate_c: int = 50,
        temperature_led_consecutive_polls: int = 2,
    ) -> None:
        self.controller = controller
        self.temperature_led_on_c = int(temperature_led_on_c)
        self.temperature_led_off_c = int(temperature_led_off_c)
        self.temperature_led_immediate_c = int(temperature_led_immediate_c)
        self.temperature_led_consecutive_polls = int(
            temperature_led_consecutive_polls
        )
        if not (
            self.temperature_led_off_c < self.temperature_led_on_c
            <= self.temperature_led_immediate_c
        ):
            raise ValueError("Invalid bay LED temperature thresholds")
        if self.temperature_led_consecutive_polls < 1:
            raise ValueError("Bay LED consecutive polls must be positive")
        self._hot_polls: dict[int, int] = {}
        self._observed_bays: set[int] = set()

        if clear_on_start:
            try:
                self.controller.clear_all()
                for bay in range(1, 7):
                    self.controller.set_error(
                        bay,
                        False,
                        force=True,
                    )
            except Exception:
                LOGGER.exception(
                    "Could not initialize bay warning/fault LEDs"
                )

    def __call__(self, event) -> bool:
        if (
            getattr(event, "category", None)
            != Category.STORAGE
        ):
            return False

        if (
            getattr(event, "source", "")
            != "storage_health_watcher"
        ):
            return False

        metadata = getattr(event, "metadata", {})

        if not isinstance(metadata, Mapping):
            return False

        bay = _integer(
            metadata.get("physical_bay")
        )

        if bay is None or not 1 <= bay <= 6:
            return False

        change_type = str(
            metadata.get("change_type", "")
        ).strip().lower()

        new_state = str(
            metadata.get("new_state", "")
        ).strip().lower()

        # Event priority describes the importance of a single observation,
        # not a persistent drive-health state. For example, a five-degree
        # temperature jump is emitted at WARNING priority even when the drive
        # remains healthy. Driving a persistent LED from that priority latches
        # the identify channel because no later health-state recovery event is
        # guaranteed. Keep physical LEDs aligned with persistent health state.
        clear = (
            change_type == "recovered"
            or new_state == "healthy"
        )

        critical = (
            not clear
            and (
                new_state == "critical"
                or change_type == "device_missing"
            )
        )

        warning = (
            not clear
            and not critical
            and new_state == "warning"
        )

        if (
            warning
            and str(metadata.get("health_message") or "")
            .strip().lower().startswith("temperature ")
        ):
            # Persistent thermal LEDs are driven from successive snapshots,
            # not the first temperature-warning event at the advisory limit.
            return False

        if not clear and not warning and not critical:
            return False

        identify_enabled = warning
        error_enabled = critical
        changed = False

        try:
            changed = bool(
                self.controller.set_identify(
                    bay,
                    identify_enabled,
                )
            ) or changed
        except Exception:
            LOGGER.exception(
                "Could not update identify LED for Bay %d",
                bay,
            )

        try:
            changed = bool(
                self.controller.set_error(
                    bay,
                    error_enabled,
                )
            ) or changed
        except Exception:
            LOGGER.exception(
                "Could not update error LED for Bay %d",
                bay,
            )

        return changed

    def reconcile_snapshot(
        self,
        snapshot: Mapping[str, Mapping[str, Any]],
    ) -> None:
        """Reconcile LEDs with fresh per-device state at each successful poll.

        Only the identify channel is cleared here. A critical error LED is
        never cleared from a potentially incomplete healthy snapshot;
        an explicit recovery event handles the error channel separately.
        Unknown, missing and ambiguous bay evidence does not clear a lamp.
        """
        records: dict[int, Mapping[str, Any]] = {}
        counts: Counter[int] = Counter()
        for record in snapshot.values():
            if not isinstance(record, Mapping):
                continue
            bay = _integer(record.get("physical_bay"))
            if bay is None or not 1 <= bay <= 6:
                continue
            counts[bay] += 1
            records[bay] = record

        for bay in sorted(records):
            if counts[bay] != 1:
                LOGGER.warning(
                    "Skipping ambiguous bay %d LED reconciliation", bay
                )
                continue

            record = records[bay]
            state = str(record.get("state") or "").lower()
            if state not in {"healthy", "warning", "critical"}:
                continue

            first_observation = bay not in self._observed_bays
            temperature = _integer(record.get("temperature_c"))
            message = str(record.get("message") or "").lower()

            try:
                if state == "critical":
                    self._hot_polls.pop(bay, None)
                    # Reassert genuine critical faults even when startup
                    # events are intentionally suppressed.
                    self.controller.set_error(bay, True)
                elif state == "healthy":
                    self._hot_polls.pop(bay, None)
                    if (
                        first_observation
                        or bay in self.controller.active_bays
                    ):
                        self.controller.set_identify(
                            bay, False, force=first_observation
                        )
                elif not message.startswith("temperature "):
                    self._hot_polls.pop(bay, None)
                    self.controller.set_identify(bay, True)
                elif temperature is not None:
                    if temperature >= self.temperature_led_on_c:
                        self._hot_polls[bay] = (
                            self._hot_polls.get(bay, 0) + 1
                        )
                        if (
                            temperature >= self.temperature_led_immediate_c
                            or self._hot_polls[bay]
                            >= self.temperature_led_consecutive_polls
                        ):
                            self.controller.set_identify(bay, True)
                    else:
                        self._hot_polls.pop(bay, None)
                        if (
                            temperature <= self.temperature_led_off_c
                            and (
                                first_observation
                                or bay in self.controller.active_bays
                            )
                        ):
                            self.controller.set_identify(
                                bay, False, force=first_observation
                            )
                self._observed_bays.add(bay)
            except Exception:
                LOGGER.exception(
                    "Could not reconcile Bay %d storage-health LED", bay
                )


__all__ = ["StorageBayIndicator"]
