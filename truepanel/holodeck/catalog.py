"""Privacy-safe built-in host profiles."""

from __future__ import annotations

import copy
from typing import Any

BATTLESTATION: dict[str, Any] = {
    "hostname": "HoloDeck-BattleStation",
    "cpu_percent": 18.0,
    "ram_percent": 41.0,
    "uptime_seconds": 864000,
    "load_average": [0.22, 0.28, 0.31],
    "cpu_temperature_c": 51.0,
    "sensors": {"cpu": 51.0, "system": 38.0},
    "telemetry_fresh": True,
    "simulation": True,
    "pools": [
        {"name": "HDDs", "size": "42T", "used": "24T", "free": "18T", "capacity": "57%", "health": "ONLINE"},
        {"name": "SSDs", "size": "910G", "used": "220G", "free": "690G", "capacity": "24%", "health": "ONLINE"},
    ],
    "temps": [{"drive": f"disk{number}", "temp": 35 + number % 4} for number in range(1, 7)],
    "alerts": [],
    "network": {
        "enp115s0": {"kind": "lan", "link_up": False, "operstate": "DOWN", "position": 1, "primary": False},
        "enp116s0": {"kind": "lan", "link_up": True, "operstate": "UP", "position": 2, "primary": True, "address": "192.0.2.10"},
        "enp120s0": {"kind": "lan", "link_up": False, "operstate": "DOWN", "position": 3, "primary": False},
        "enp121s0": {"kind": "lan", "link_up": False, "operstate": "DOWN", "position": 4, "primary": False},
        "tailscale0": {"kind": "tailscale", "link_up": True, "operstate": "UNKNOWN", "primary": False, "address": "100.64.0.10"},
    },
    "fans": {
        "connected": True,
        "fan_channels": [
            {"number": 1, "rpm": 1510, "pwm": 185, "alarm": False},
            {"number": 2, "rpm": 1470, "pwm": 185, "alarm": False},
            {"number": 3, "rpm": 980, "pwm": None, "alarm": False},
        ],
    },
    "lcd": {"connected": True, "controller": "A125", "port": "virtual:a125"},
    "enclosure": {
        "bays": [
            {"bay": number, "device": f"disk{number}", "health": "ONLINE", "present": True}
            for number in range(1, 7)
        ]
    },
}


HOSTS = {"battlestation": BATTLESTATION}


def host_fixture(name: str) -> dict[str, Any]:
    try:
        return copy.deepcopy(HOSTS[name])
    except KeyError as error:
        raise ValueError(f"unknown HoloDeck host: {name}") from error
