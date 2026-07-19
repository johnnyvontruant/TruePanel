"""
Translate structured storage-health events into bay identify LED state.
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
    Maintain the verified identify LED for each unhealthy physical bay.

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
            except Exception:
                LOGGER.exception(
                    "Could not initialize bay identify LEDs"
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

        clear = (
            change_type == "recovered"
            or new_state == "healthy"
        )

        activate = (
            not clear
            and getattr(
                event,
                "priority",
                Priority.NONE,
            )
            >= Priority.WARNING
        )

        if not clear and not activate:
            return False

        try:
            return self.controller.set_identify(
                bay,
                activate,
            )
        except Exception:
            LOGGER.exception(
                "Could not update identify LED for Bay %d",
                bay,
            )
            return False


__all__ = ["StorageBayIndicator"]
