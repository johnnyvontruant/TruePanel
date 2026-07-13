"""
Runtime integration for TruePanel historical telemetry.
"""

from __future__ import annotations

import logging
from typing import Any

from .service import HistoryService


LOGGER = logging.getLogger("truepanel.history.runtime")


class TelemetryRecorder:
    """
    Small failure-isolation layer around HistoryService.

    Collector and LCD operation must continue even when history storage is
    unavailable, read-only, full, or temporarily corrupt.
    """

    def __init__(self, config=None):
        self.service = HistoryService(config or {})
        self.recorded_samples = 0
        self.skipped_samples = 0
        self.failed_samples = 0

    def record(
        self,
        state: dict[str, Any],
        alert_count: int = 0,
        force: bool = False,
    ) -> bool:
        try:
            written = self.service.record_state(
                state,
                alert_count=alert_count,
                force=force,
            )
        except Exception as error:
            self.failed_samples += 1
            LOGGER.warning("Telemetry recording failed: %s", error)
            return False

        if written:
            self.recorded_samples += 1
        else:
            self.skipped_samples += 1

        return written

    def stats(self):
        result = self.service.stats()
        result.update(
            {
                "runtime_recorded": self.recorded_samples,
                "runtime_skipped": self.skipped_samples,
                "runtime_failed": self.failed_samples,
            }
        )
        return result
