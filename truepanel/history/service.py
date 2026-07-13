"""
TruePanel historical telemetry service.
"""

from __future__ import annotations

import logging

from .extract import sample_from_state
from .store import HistoryStore


LOGGER = logging.getLogger("truepanel.history")


class HistoryService:
    def __init__(self, config=None):
        self.config = config or {}
        self.store = HistoryStore(self.config)

    def record_state(
        self,
        state,
        alert_count=0,
        force=False,
    ):
        sample = sample_from_state(
            state,
            alert_count=alert_count,
        )

        try:
            return self.store.append(
                sample,
                force=force,
            )
        except Exception as error:
            LOGGER.warning(
                "Unable to record telemetry: %s",
                error,
            )
            return False

    def samples(self, limit=None, since=None):
        return self.store.read(
            limit=limit,
            since=since,
        )

    def compact(self):
        return self.store.compact()

    def clear(self):
        self.store.clear()

    def stats(self):
        return self.store.stats()
