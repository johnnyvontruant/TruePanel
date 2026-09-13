"""
Translate structured storage-health events into physical bay LED state.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from .constants import Category, Priority

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
    ) -> None:
        self.controller = controller

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

        priority = getattr(
            event,
            "priority",
            Priority.NONE,
        )

        clear = (
            change_type == "recovered"
            or new_state == "healthy"
        )

        critical = (
            not clear
            and (
                new_state == "critical"
                or priority >= Priority.CRITICAL
            )
        )

        warning = (
            not clear
            and not critical
            and (
                new_state == "warning"
                or priority >= Priority.WARNING
            )
        )

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


__all__ = ["StorageBayIndicator"]
