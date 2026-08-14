"""Deterministic, offline incident narration for TruePanel Black Box replay."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from .black_box import (
    BlackBoxFrame,
    BlackBoxReplay,
    sanitize_black_box_value,
)


_HEALTHY_WORDS = {
    "available",
    "good",
    "healthy",
    "ok",
    "online",
    "pass",
    "ready",
    "running",
}
_ALERT_SEVERITIES = {"critical", "error", "warning"}
_STORAGE_HEALTH_KEYS = ("pool_health", "health", "status", "state")


@dataclass(frozen=True)
class BlackBoxIncident:
    """One observed state transition from a sanitized Black Box replay."""

    captured_at: float
    sequence: int
    domain: str
    severity: str
    summary: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class BlackBoxIncidentNarrator:
    """Explain meaningful recorded transitions without touching live runtime.

    Narration is deterministic and evidence-bound: it describes only changes
    visible in adjacent sanitized Black Box frames. It does not infer causes,
    perform hardware access, call external services, or execute callbacks.
    """

    def __init__(
        self,
        replay: BlackBoxReplay,
        *,
        max_events: int = 512,
        max_summary_chars: int = 240,
    ):
        if not isinstance(replay, BlackBoxReplay):
            raise TypeError("replay must be a BlackBoxReplay")
        self.replay = replay
        self.max_events = max(1, min(int(max_events), 4096))
        self.max_summary_chars = max(40, min(int(max_summary_chars), 1000))

    def incidents(self) -> tuple[BlackBoxIncident, ...]:
        events: list[BlackBoxIncident] = []
        frames = self.replay.frames

        for previous, current in zip(frames, frames[1:]):
            for event in self._frame_transitions(previous, current):
                events.append(event)
                if len(events) >= self.max_events:
                    return tuple(events)

        return tuple(events)

    def timeline(self) -> tuple[str, ...]:
        """Return compact deterministic lines suitable for support reports."""

        return tuple(
            (
                f"t={event.captured_at:.3f} seq={event.sequence} "
                f"[{event.severity}] {event.domain}: {event.summary}"
            )
            for event in self.incidents()
        )

    def _frame_transitions(
        self,
        previous: BlackBoxFrame,
        current: BlackBoxFrame,
    ) -> Iterable[BlackBoxIncident]:
        yield from self._storage_events(previous, current)
        yield from self._fan_events(previous, current)
        yield from self._alert_events(previous, current)
        yield from self._mission_control_events(previous, current)
        yield from self._lcd_events(previous, current)
        yield from self._button_events(previous, current)

    def _event(
        self,
        frame: BlackBoxFrame,
        domain: str,
        severity: str,
        summary: str,
    ) -> BlackBoxIncident:
        safe = sanitize_black_box_value(str(summary))
        safe = str(safe).replace("\n", " ").strip()
        if len(safe) > self.max_summary_chars:
            safe = safe[: self.max_summary_chars - 1].rstrip() + "…"

        return BlackBoxIncident(
            captured_at=frame.captured_at,
            sequence=frame.sequence,
            domain=domain,
            severity=severity,
            summary=safe,
        )

    def _storage_events(self, previous, current):
        before = self._first_value(previous.storage, _STORAGE_HEALTH_KEYS)
        after = self._first_value(current.storage, _STORAGE_HEALTH_KEYS)
        if before is None or after is None or before == after:
            return ()

        severity = "info" if self._looks_healthy(after) else "warning"
        return (
            self._event(
                current,
                "storage",
                severity,
                f"Storage health changed from {before} to {after}.",
            ),
        )

    def _fan_events(self, previous, current):
        before = self._fan_rpms(previous.fan)
        after = self._fan_rpms(current.fan)
        events: list[BlackBoxIncident] = []

        for label in sorted(before.keys() & after.keys()):
            old = before[label]
            new = after[label]
            if old > 0 and new <= 0:
                events.append(
                    self._event(
                        current,
                        "fan",
                        "warning",
                        f"{label} RPM changed from {old:g} to {new:g}.",
                    )
                )
            elif old <= 0 and new > 0:
                events.append(
                    self._event(
                        current,
                        "fan",
                        "info",
                        f"{label} RPM recovered from {old:g} to {new:g}.",
                    )
                )

        return tuple(events)

    def _alert_events(self, previous, current):
        before = self._alert_index(previous.alerts)
        after = self._alert_index(current.alerts)
        events: list[BlackBoxIncident] = []

        for key in sorted(after.keys() - before.keys()):
            alert = after[key]
            severity = self._alert_severity(alert)
            message = self._alert_message(alert)
            events.append(
                self._event(
                    current,
                    "alerts",
                    severity,
                    f"Alert observed: {message}",
                )
            )

        for key in sorted(before.keys() - after.keys()):
            alert = before[key]
            message = self._alert_message(alert)
            events.append(
                self._event(
                    current,
                    "alerts",
                    "info",
                    f"Alert cleared: {message}",
                )
            )

        return tuple(events)

    def _mission_control_events(self, previous, current):
        return self._availability_events(
            previous.mission_control,
            current.mission_control,
            frame=current,
            domain="mission_control",
            label="Mission Control",
        )

    def _lcd_events(self, previous, current):
        events = list(
            self._availability_events(
                previous.lcd,
                current.lcd,
                frame=current,
                domain="lcd",
                label="LCD",
            )
        )

        before_stale = previous.lcd.get("stale")
        after_stale = current.lcd.get("stale")
        if (
            isinstance(before_stale, bool)
            and isinstance(after_stale, bool)
            and before_stale != after_stale
        ):
            events.append(
                self._event(
                    current,
                    "lcd",
                    "warning" if after_stale else "info",
                    "LCD state became stale."
                    if after_stale
                    else "LCD state returned to fresh.",
                )
            )

        return tuple(events)

    def _button_events(self, previous, current):
        before = previous.buttons.get("button_reports")
        after = current.buttons.get("button_reports")
        if not self._is_number(before) or not self._is_number(after):
            return ()
        if after <= before:
            return ()

        count = int(after - before)
        noun = "report" if count == 1 else "reports"
        return (
            self._event(
                current,
                "buttons",
                "info",
                f"Observed {count} new front-panel button {noun}.",
            ),
        )

    def _availability_events(
        self,
        previous: Mapping[str, Any],
        current: Mapping[str, Any],
        *,
        frame: BlackBoxFrame,
        domain: str,
        label: str,
    ):
        for key in ("available", "healthy"):
            before = previous.get(key)
            after = current.get(key)
            if (
                isinstance(before, bool)
                and isinstance(after, bool)
                and before != after
            ):
                return (
                    self._event(
                        frame,
                        domain,
                        "info" if after else "warning",
                        f"{label} became available."
                        if after
                        else f"{label} became unavailable.",
                    ),
                )
        return ()

    @staticmethod
    def _first_value(mapping, keys):
        for key in keys:
            value = mapping.get(key)
            if value is not None:
                return value
        return None

    @staticmethod
    def _looks_healthy(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in _HEALTHY_WORDS

    @staticmethod
    def _is_number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    @classmethod
    def _fan_rpms(cls, fan: Mapping[str, Any]) -> dict[str, float]:
        result: dict[str, float] = {}
        rpm = fan.get("rpm")

        if isinstance(rpm, (list, tuple)):
            for index, value in enumerate(rpm, start=1):
                if cls._is_number(value):
                    result[f"Fan {index}"] = float(value)
        elif isinstance(rpm, Mapping):
            for key, value in rpm.items():
                if cls._is_number(value):
                    result[str(key)] = float(value)

        for key, value in fan.items():
            normalized = str(key).lower()
            if (
                normalized.endswith("_rpm")
                and cls._is_number(value)
            ):
                result[str(key)] = float(value)

        return result

    @staticmethod
    def _alert_index(alerts: Iterable[Mapping[str, Any]]):
        result = {}
        for alert in alerts:
            safe = sanitize_black_box_value(dict(alert))
            key = json.dumps(safe, sort_keys=True, separators=(",", ":"))
            result[key] = safe
        return result

    @staticmethod
    def _alert_severity(alert: Mapping[str, Any]) -> str:
        severity = str(alert.get("severity", "warning")).strip().lower()
        return severity if severity in _ALERT_SEVERITIES else "warning"

    @staticmethod
    def _alert_message(alert: Mapping[str, Any]) -> str:
        for key in ("message", "summary", "title", "name"):
            value = alert.get(key)
            if value:
                return str(value)
        return "recorded alert"
