"""Validated scenario documents for the TruePanel Digital Twin."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

MAX_SCENARIO_EVENTS = 1_000

SUPPORTED_EVENTS = frozenset(
    {
        "temperature",
        "fan_stall",
        "fan_recover",
        "disk_fault",
        "disk_recover",
        "disk_remove",
        "disk_insert",
        "network_down",
        "network_up",
        "lcd_disconnect",
        "lcd_connect",
        "telemetry_stale",
        "telemetry_fresh",
        "pool_health",
    }
)


@dataclass(frozen=True, order=True)
class ScenarioEvent:
    at: float
    type: str = field(compare=False)
    values: dict[str, Any] = field(default_factory=dict, compare=False)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ScenarioEvent:
        if not isinstance(payload, dict):
            raise ValueError("scenario events must be mappings")
        event_type = str(payload.get("type", "")).strip().lower()
        if event_type not in SUPPORTED_EVENTS:
            raise ValueError(f"unsupported HoloDeck event: {event_type or '<empty>'}")
        at = float(payload.get("at", 0.0))

        if not math.isfinite(at):
            raise ValueError(
                "scenario event time must be finite"
            )

        if at < 0:
            raise ValueError(
                "scenario event time cannot be negative"
            )
        return cls(
            at=at,
            type=event_type,
            values={key: value for key, value in payload.items() if key not in {"at", "type"}},
        )


@dataclass(frozen=True)
class Scenario:
    name: str
    host: str
    events: tuple[ScenarioEvent, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Scenario:
        if not isinstance(payload, dict):
            raise ValueError("scenario document must be a mapping")
        name = str(payload.get("name", "scenario")).strip() or "scenario"
        host = str(payload.get("host", "battlestation")).strip()
        if not host or Path(host).name != host:
            raise ValueError("scenario host must be a fixture name")
        raw_events = payload.get("events", [])
        if not isinstance(raw_events, list):
            raise ValueError(
                "scenario events must be a list"
            )

        if len(raw_events) > MAX_SCENARIO_EVENTS:
            raise ValueError(
                "scenario event limit exceeded: "
                f"{len(raw_events)} > "
                f"{MAX_SCENARIO_EVENTS}"
            )

        events = tuple(
            sorted(
                ScenarioEvent.from_dict(item)
                for item in raw_events
            )
        )
        return cls(name=name, host=host, events=events)


def load_scenario(path: str | Path) -> Scenario:
    candidate = Path(path)
    text = candidate.read_text(encoding="utf-8")
    if candidate.suffix.lower() == ".json":
        payload = json.loads(text)
    else:
        payload = yaml.safe_load(text)
    return Scenario.from_dict(payload)