"""
Bounded JSONL telemetry storage for TruePanel.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Iterable

from .models import TelemetrySample


LOGGER = logging.getLogger("truepanel.history")


class HistoryStore:
    def __init__(self, config=None):
        config = config or {}

        self.enabled = bool(config.get("enabled", True))
        self.path = Path(
            config.get(
                "path",
                "/var/lib/truepanel/history/telemetry.jsonl",
            )
        )

        self.sample_interval = max(
            1.0,
            float(config.get("sample_interval", 60)),
        )

        self.retention_days = max(
            1,
            int(config.get("retention_days", 30)),
        )

        self.max_samples = max(
            100,
            int(config.get("max_samples", 50000)),
        )

        self.compact_every = max(
            10,
            int(config.get("compact_every", 250)),
        )

        self.flush = bool(config.get("flush", False))

        self._lock = threading.RLock()
        self._last_sample_time = 0.0
        self._writes_since_compaction = 0

    def ensure_parent(self):
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    def should_record(self, timestamp=None):
        if not self.enabled:
            return False

        timestamp = float(timestamp or time.time())

        if timestamp - self._last_sample_time < self.sample_interval:
            return False

        return True

    def append(self, sample, force=False):
        if not self.enabled:
            return False

        if not isinstance(sample, TelemetrySample):
            sample = TelemetrySample.from_dict(dict(sample))

        if not force and not self.should_record(sample.timestamp):
            return False

        encoded = json.dumps(
            sample.as_dict(),
            separators=(",", ":"),
            sort_keys=True,
        )

        with self._lock:
            self.ensure_parent()

            with self.path.open(
                "a",
                encoding="utf-8",
            ) as handle:
                handle.write(encoded + "\n")

                if self.flush:
                    handle.flush()
                    os.fsync(handle.fileno())

            self._last_sample_time = sample.timestamp
            self._writes_since_compaction += 1

            if self._writes_since_compaction >= self.compact_every:
                self.compact()
                self._writes_since_compaction = 0

        return True

    def iter_samples(self) -> Iterable[TelemetrySample]:
        if not self.path.exists():
            return

        with self.path.open(
            encoding="utf-8",
            errors="replace",
        ) as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()

                if not line:
                    continue

                try:
                    data = json.loads(line)
                    yield TelemetrySample.from_dict(data)
                except Exception as error:
                    LOGGER.warning(
                        "Skipping invalid history line %s: %s",
                        line_number,
                        error,
                    )

    def read(
        self,
        limit=None,
        since=None,
    ):
        samples = list(self.iter_samples() or [])

        if since is not None:
            since = float(since)
            samples = [
                sample
                for sample in samples
                if sample.timestamp >= since
            ]

        if limit is not None:
            samples = samples[-max(0, int(limit)):]

        return samples

    def latest(self, limit=1):
        return self.read(limit=limit)

    def count(self):
        return sum(1 for _ in self.iter_samples() or [])

    def stats(self):
        samples = self.read()

        return {
            "enabled": self.enabled,
            "path": str(self.path),
            "exists": self.path.exists(),
            "samples": len(samples),
            "first_timestamp": (
                samples[0].timestamp
                if samples
                else None
            ),
            "last_timestamp": (
                samples[-1].timestamp
                if samples
                else None
            ),
            "size_bytes": (
                self.path.stat().st_size
                if self.path.exists()
                else 0
            ),
            "sample_interval": self.sample_interval,
            "retention_days": self.retention_days,
            "max_samples": self.max_samples,
        }

    def compact(self):
        if not self.path.exists():
            return 0

        cutoff = time.time() - (
            self.retention_days * 24 * 60 * 60
        )

        retained = [
            sample
            for sample in self.iter_samples() or []
            if sample.timestamp >= cutoff
        ]

        retained = retained[-self.max_samples:]

        self.ensure_parent()
        temporary = self.path.with_suffix(
            self.path.suffix + ".tmp"
        )

        with temporary.open(
            "w",
            encoding="utf-8",
        ) as handle:
            for sample in retained:
                handle.write(
                    json.dumps(
                        sample.as_dict(),
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    + "\n"
                )

            handle.flush()
            os.fsync(handle.fileno())

        temporary.replace(self.path)
        return len(retained)

    def clear(self):
        with self._lock:
            if self.path.exists():
                self.path.unlink()

            self._last_sample_time = 0.0
            self._writes_since_compaction = 0
