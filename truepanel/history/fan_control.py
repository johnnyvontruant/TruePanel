"""
Append-only fan-control event history.

This recorder is intentionally independent from periodic telemetry history.
Control events are sparse state transitions and must never block or influence
fan-control execution.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Mapping


LOGGER = logging.getLogger(__name__)

DEFAULT_FAN_CONTROL_HISTORY_PATH = Path(
    "/var/lib/truepanel/history/fan-control.jsonl"
)


class FanControlHistory:
    def __init__(
        self,
        path: str | Path = (
            DEFAULT_FAN_CONTROL_HISTORY_PATH
        ),
        *,
        enabled: bool = True,
        retention_days: int = 30,
        max_events: int = 5000,
        compact_every: int = 100,
        flush: bool = False,
        clock=time.time,
    ):
        self.path = Path(path)
        self.enabled = bool(enabled)
        self.retention_days = max(
            1,
            int(retention_days),
        )
        self.max_events = max(
            1,
            int(max_events),
        )
        self.compact_every = max(
            1,
            int(compact_every),
        )
        self.flush = bool(flush)
        self.clock = clock
        self._lock = threading.RLock()
        self._writes_since_compaction = 0

    def ensure_parent(self) -> None:
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    def append(
        self,
        event: Mapping[str, Any],
    ) -> bool:
        if not self.enabled:
            return False

        payload = dict(event)
        payload.setdefault(
            "schema_version",
            1,
        )
        payload.setdefault(
            "event_type",
            "fan_control",
        )
        payload.setdefault(
            "timestamp",
            float(self.clock()),
        )

        encoded = json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        )

        with self._lock:
            self.ensure_parent()

            with self.path.open(
                "a",
                encoding="utf-8",
            ) as handle:
                handle.write(
                    encoded + "\n"
                )

                if self.flush:
                    handle.flush()
                    os.fsync(
                        handle.fileno()
                    )

            self._writes_since_compaction += 1

            if (
                self._writes_since_compaction
                >= self.compact_every
            ):
                self.compact()
                self._writes_since_compaction = 0

        return True

    def iter_events(
        self,
    ) -> Iterable[dict[str, Any]]:
        if not self.path.exists():
            return

        with self.path.open(
            encoding="utf-8",
            errors="replace",
        ) as handle:
            for line_number, raw_line in enumerate(
                handle,
                start=1,
            ):
                line = raw_line.strip()

                if not line:
                    continue

                try:
                    payload = json.loads(
                        line
                    )
                except json.JSONDecodeError as error:
                    LOGGER.warning(
                        "Skipping invalid fan history "
                        "line %s: %s",
                        line_number,
                        error,
                    )
                    continue

                if isinstance(
                    payload,
                    dict,
                ):
                    yield payload

    def read(
        self,
        *,
        limit: int | None = None,
        since: float | None = None,
    ) -> list[dict[str, Any]]:
        events = list(
            self.iter_events()
            or []
        )

        if since is not None:
            cutoff = float(since)
            events = [
                event
                for event in events
                if float(
                    event.get(
                        "timestamp",
                        0.0,
                    )
                    or 0.0
                )
                >= cutoff
            ]

        if limit is not None:
            events = events[
                -max(
                    0,
                    int(limit),
                ):
            ]

        return events

    def compact(self) -> int:
        if not self.path.exists():
            return 0

        cutoff = float(
            self.clock()
        ) - (
            self.retention_days
            * 24
            * 60
            * 60
        )

        retained = [
            event
            for event in (
                self.iter_events()
                or []
            )
            if float(
                event.get(
                    "timestamp",
                    0.0,
                )
                or 0.0
            )
            >= cutoff
        ]

        retained = retained[
            -self.max_events:
        ]

        self.ensure_parent()

        temporary = self.path.with_suffix(
            self.path.suffix + ".tmp"
        )

        with temporary.open(
            "w",
            encoding="utf-8",
        ) as handle:
            for event in retained:
                handle.write(
                    json.dumps(
                        event,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    + "\n"
                )

            handle.flush()
            os.fsync(
                handle.fileno()
            )

        temporary.replace(
            self.path
        )

        return len(retained)


def event_from_decision(
    decision,
    *,
    source: str,
    telemetry: Mapping[str, Any] | None = None,
    timestamp: float | None = None,
) -> dict[str, Any]:
    telemetry = dict(
        telemetry
        or {}
    )
    fan_status = dict(
        telemetry.get(
            "fan_status",
            {},
        )
        or {}
    )

    rpm = {}
    modes = {}
    pwm = {}

    for channel in (
        fan_status.get(
            "fan_channels",
            [],
        )
        or []
    ):
        if not isinstance(
            channel,
            Mapping,
        ):
            continue

        try:
            number = int(
                channel.get(
                    "number",
                    0,
                )
                or 0
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        if number <= 0:
            continue

        rpm[str(number)] = int(
            channel.get(
                "rpm",
                0,
            )
            or 0
        )
        pwm[str(number)] = int(
            channel.get(
                "pwm",
                0,
            )
            or 0
        )
        modes[str(number)] = str(
            channel.get(
                "pwm_mode",
                "Unavailable",
            )
        )

    return {
        "schema_version": 1,
        "event_type": "fan_control",
        "timestamp": (
            float(timestamp)
            if timestamp is not None
            else time.time()
        ),
        "source": str(source),
        "requested_profile": (
            decision.requested_profile.value
        ),
        "effective_profile": (
            decision.effective_profile.value
        ),
        "decision_pwm": decision.pwm,
        "force_automatic": bool(
            decision.force_automatic
        ),
        "accepted": bool(
            decision.accepted
        ),
        "fan_rpm": rpm,
        "fan_pwm": pwm,
        "fan_modes": modes,
        "temperatures_c": [
            float(value)
            for value in (
                telemetry.get(
                    "temperatures_c",
                    (),
                )
                or ()
            )
        ],
        "telemetry_fresh": bool(
            telemetry.get(
                "telemetry_fresh",
                True,
            )
        ),
        "reason": str(
            decision.reason
        ),
    }


__all__ = [
    "DEFAULT_FAN_CONTROL_HISTORY_PATH",
    "FanControlHistory",
    "event_from_decision",
]
