"""Durable thermal commissioning lifecycle history."""

from __future__ import annotations

import json
import time
from pathlib import Path


DEFAULT_THERMAL_COMMISSIONING_HISTORY_PATH = Path(
    "/var/lib/truepanel/history/"
    "thermal-commissioning.jsonl"
)

THERMAL_COMMISSIONING_ACTIONS = (
    "supervised_started",
    "supervised_disarmed",
    "supervised_expired",
    "supervised_safety_cancelled",
    "automatic_lease_started",
    "automatic_lease_renewed",
    "automatic_lease_cancelled",
    "automatic_lease_expired",
    "automatic_lease_safety_cancelled",
)


def commissioning_event(
    *,
    lifecycle_action,
    reason,
    commissioning_state,
    active_profile,
    control_authority,
    lease_remaining=0.0,
    timestamp=None,
):
    """Build a normalized commissioning lifecycle event."""

    action = str(lifecycle_action)

    if action not in THERMAL_COMMISSIONING_ACTIONS:
        raise ValueError(
            f"Unknown commissioning lifecycle action: {action}"
        )

    return {
        "schema_version": 1,
        "event_type": "thermal_commissioning",
        "timestamp": float(
            time.time()
            if timestamp is None
            else timestamp
        ),
        "lifecycle_action": action,
        "reason": str(reason),
        "commissioning_state": str(
            commissioning_state
        ),
        "active_profile": str(
            active_profile
        ),
        "control_authority": str(
            control_authority
        ),
        "lease_remaining": max(
            0.0,
            float(
                lease_remaining
                or 0.0
            ),
        ),
    }


class ThermalCommissioningHistory:
    """Append-only bounded JSONL commissioning history."""

    def __init__(
        self,
        path=DEFAULT_THERMAL_COMMISSIONING_HISTORY_PATH,
        *,
        enabled=True,
        maximum_events=1000,
        clock=None,
    ):
        self.path = Path(path)
        self.enabled = bool(enabled)
        self.maximum_events = max(
            1,
            int(maximum_events),
        )
        self.clock = clock or time.time

    def append(self, event):
        if not self.enabled:
            return False

        payload = dict(
            event
            or {}
        )

        payload.setdefault(
            "schema_version",
            1,
        )
        payload.setdefault(
            "event_type",
            "thermal_commissioning",
        )
        payload.setdefault(
            "timestamp",
            float(self.clock()),
        )

        payload["timestamp"] = float(
            payload["timestamp"]
        )

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.path.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                json.dumps(
                    payload,
                    sort_keys=True,
                )
            )
            handle.write("\n")

        self._prune()
        return True

    def read(self, *, limit=20):
        if not self.path.exists():
            return []

        events = []

        try:
            lines = self.path.read_text(
                encoding="utf-8"
            ).splitlines()
        except OSError:
            return []

        for line in lines:
            try:
                event = json.loads(line)
            except (
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):
                continue

            if not isinstance(event, dict):
                continue

            try:
                event["timestamp"] = float(
                    event.get(
                        "timestamp",
                        0.0,
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            events.append(event)

        bounded_limit = max(
            1,
            int(limit),
        )

        return events[
            -bounded_limit:
        ]

    def _prune(self):
        events = self.read(
            limit=self.maximum_events + 1
        )

        if len(events) <= self.maximum_events:
            return

        retained = events[
            -self.maximum_events:
        ]

        temporary_path = self.path.with_suffix(
            self.path.suffix + ".tmp"
        )

        with temporary_path.open(
            "w",
            encoding="utf-8",
        ) as handle:
            for event in retained:
                handle.write(
                    json.dumps(
                        event,
                        sort_keys=True,
                    )
                )
                handle.write("\n")

        temporary_path.replace(
            self.path
        )


__all__ = [
    "DEFAULT_THERMAL_COMMISSIONING_HISTORY_PATH",
    "THERMAL_COMMISSIONING_ACTIONS",
    "ThermalCommissioningHistory",
    "commissioning_event",
]
