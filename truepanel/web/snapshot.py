"""Read-only data services for TruePanel Mission Control."""

from __future__ import annotations

import json
import platform
import socket
import time
from pathlib import Path
from typing import Any

from collector import TruePanelCollector
from truepanel.config.loader import load_config
from truepanel.hardware.fans import (
    get_status as get_fan_status,
)


DEFAULT_HISTORY_PATH = Path(
    "/var/lib/truepanel/history/telemetry.jsonl"
)


def _safe_number(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_list(value: Any) -> list:
    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    return []


class SnapshotService:
    """Build JSON-safe read-only dashboard payloads."""

    def __init__(
        self,
        collector=None,
        config=None,
        history_path=None,
        clock=None,
    ):
        self.collector = (
            collector
            or TruePanelCollector()
        )

        self.config = (
            config
            or load_config()
        )

        self.clock = (
            clock
            or time.time
        )

        history_config = self.config.get(
            "history",
            {},
        )

        configured_path = history_config.get(
            "path",
            DEFAULT_HISTORY_PATH,
        )

        self.history_path = Path(
            history_path
            or configured_path
        )

    def status(self) -> dict[str, Any]:
        state = dict(
            self.collector.update()
            or {}
        )

        return {
            "schema_version": 1,
            "read_only": True,
            "timestamp": self.clock(),
            "system": self._system_payload(
                state
            ),
            "storage": self._storage_payload(
                state
            ),
            "network": self._network_payload(
                state
            ),
            "fans": self._fan_payload(),
            "capabilities": (
                self.capabilities()
            ),
        }

    def capabilities(self) -> dict[str, Any]:
        hardware = self.config.get(
            "hardware",
            {},
        )

        night_mode = self.config.get(
            "night_mode",
            {},
        )

        return {
            "dashboard": {
                "status": True,
                "history": True,
                "live_refresh": True,
            },
            "configuration": {
                "available": False,
                "planned": True,
                "night_mode_configured": bool(
                    night_mode
                ),
            },
            "hardware_controls": {
                "available": False,
                "planned": True,
                "fan_telemetry": True,
                "fan_control": False,
                "bay_leds": bool(
                    hardware.get(
                        "bay_leds"
                    )
                ),
                "buzzer": bool(
                    self.config.get(
                        "buzzer"
                    )
                ),
            },
            "safety": {
                "read_only": True,
                "remote_writes_enabled": (
                    False
                ),
                "direct_device_access": (
                    False
                ),
            },
        }

    def history(
        self,
        limit: int = 240,
    ) -> dict[str, Any]:
        limit = max(
            1,
            min(
                int(limit),
                2000,
            ),
        )

        samples = []

        try:
            with self.history_path.open(
                "r",
                encoding="utf-8",
            ) as handle:
                for raw_line in handle:
                    line = raw_line.strip()

                    if not line:
                        continue

                    try:
                        payload = json.loads(
                            line
                        )
                    except json.JSONDecodeError:
                        continue

                    if isinstance(
                        payload,
                        dict,
                    ):
                        samples.append(
                            payload
                        )
        except FileNotFoundError:
            samples = []
        except OSError:
            samples = []

        samples = samples[-limit:]

        return {
            "schema_version": 1,
            "read_only": True,
            "path": str(
                self.history_path
            ),
            "count": len(samples),
            "samples": samples,
        }

    @staticmethod
    def _system_payload(
        state: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "hostname": (
                socket.gethostname()
            ),
            "platform": (
                platform.system()
            ),
            "machine": (
                platform.machine()
            ),
            "cpu_percent": _safe_number(
                state.get(
                    "cpu_percent"
                )
            ),
            "ram_percent": _safe_number(
                state.get(
                    "ram_percent"
                )
            ),
            "uptime_seconds": _safe_number(
                state.get(
                    "uptime_seconds"
                )
            ),
            "load_average": _safe_list(
                state.get(
                    "load_average"
                )
            ),
        }

    @staticmethod
    def _storage_payload(
        state: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "pools": _safe_list(
                state.get(
                    "pools"
                )
            ),
            "temperatures": _safe_list(
                state.get(
                    "temps"
                )
            ),
            "alerts": _safe_list(
                state.get(
                    "alerts"
                )
            ),
        }

    @staticmethod
    def _network_payload(
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidates = (
            state.get(
                "network_interfaces"
            )
            or state.get(
                "interfaces"
            )
            or state.get(
                "ip_addresses"
            )
            or []
        )

        if isinstance(
            candidates,
            dict,
        ):
            return [
                {
                    "name": str(name),
                    "address": value,
                }
                for name, value
                in candidates.items()
            ]

        if isinstance(
            candidates,
            list,
        ):
            return candidates

        return []

    @staticmethod
    def _fan_payload() -> dict[str, Any]:
        try:
            payload = dict(
                get_fan_status()
                or {}
            )
        except Exception:
            payload = {}

        return {
            "available": bool(payload),
            "fan1_rpm": int(
                payload.get(
                    "fan1_rpm",
                    0,
                )
                or 0
            ),
            "fan2_rpm": int(
                payload.get(
                    "fan2_rpm",
                    0,
                )
                or 0
            ),
            "pwm1": int(
                payload.get(
                    "pwm1",
                    0,
                )
                or 0
            ),
            "pwm2": int(
                payload.get(
                    "pwm2",
                    0,
                )
                or 0
            ),
            "pwm1_mode": str(
                payload.get(
                    "pwm1_mode",
                    "Unavailable",
                )
            ),
            "pwm2_mode": str(
                payload.get(
                    "pwm2_mode",
                    "Unavailable",
                )
            ),
        }
