"""Built-in deterministic incident missions for the TruePanel Digital Twin."""

from __future__ import annotations

import copy
from typing import Any

from .scenario import Scenario

_MISSIONS: dict[str, dict[str, Any]] = {
    "thermal-ramp": {
        "name": "thermal-ramp",
        "host": "battlestation",
        "events": [
            {"at": 60, "type": "temperature", "sensor": "cpu", "value": 58},
            {"at": 120, "type": "temperature", "sensor": "cpu", "value": 66},
            {"at": 180, "type": "temperature", "sensor": "cpu", "value": 74},
            {"at": 240, "type": "temperature", "sensor": "cpu", "value": 62},
            {"at": 300, "type": "temperature", "sensor": "cpu", "value": 54},
        ],
    },
    "fan-stall-recovery": {
        "name": "fan-stall-recovery",
        "host": "battlestation",
        "events": [
            {"at": 30, "type": "fan_stall", "channel": 1},
            {"at": 120, "type": "fan_recover", "channel": 1, "rpm": 1510},
        ],
    },
    "drive-failure": {
        "name": "drive-failure",
        "host": "battlestation",
        "events": [
            {"at": 30, "type": "disk_fault", "bay": 3},
            {"at": 35, "type": "pool_health", "pool": "HDDs", "health": "DEGRADED"},
        ],
    },
    "drive-removal": {
        "name": "drive-removal",
        "host": "battlestation",
        "events": [
            {"at": 30, "type": "disk_remove", "bay": 3},
            {"at": 35, "type": "pool_health", "pool": "HDDs", "health": "DEGRADED"},
        ],
    },
    "network-flap": {
        "name": "network-flap",
        "host": "battlestation",
        "events": [
            {"at": 30, "type": "network_down", "interface": "enp116s0"},
            {"at": 90, "type": "network_up", "interface": "enp116s0"},
        ],
    },
    "lcd-loss-recovery": {
        "name": "lcd-loss-recovery",
        "host": "battlestation",
        "events": [
            {"at": 30, "type": "lcd_disconnect"},
            {"at": 90, "type": "lcd_connect"},
        ],
    },
    "stale-telemetry-recovery": {
        "name": "stale-telemetry-recovery",
        "host": "battlestation",
        "events": [
            {"at": 30, "type": "telemetry_stale"},
            {"at": 120, "type": "telemetry_fresh"},
        ],
    },
}


def mission_names() -> tuple[str, ...]:
    """Return built-in mission names in stable display order."""

    return tuple(_MISSIONS)


def mission_scenario(name: str) -> Scenario:
    """Build a fresh validated scenario for a named built-in mission."""

    key = str(name).strip().lower()
    try:
        payload = _MISSIONS[key]
    except KeyError as error:
        available = ", ".join(mission_names())
        raise ValueError(
            f"unknown HoloDeck mission: {name!r}; available: {available}"
        ) from error
    return Scenario.from_dict(copy.deepcopy(payload))
