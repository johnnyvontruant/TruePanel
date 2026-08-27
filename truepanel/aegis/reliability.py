"""Mission Control composition service for Project AEGIS."""

from __future__ import annotations

import math
from statistics import fmean
from typing import Any

from truepanel.oracle import OracleEngine

from .correlation import correlate_incident
from .coverage import coverage_matrix
from .rehearsal import rehearse_recovery_paths


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _average(values: list[float]) -> float | None:
    return fmean(values) if values else None


class AegisReliabilityEngine:
    """Add predictive outlook, incident correlation, and coverage evidence."""

    def __init__(self, *, oracle: OracleEngine | None = None) -> None:
        self.oracle = oracle or OracleEngine()
        self.rehearsals = rehearse_recovery_paths()
        self.matrix = coverage_matrix(self.rehearsals)
        self._sequence = 0

    @staticmethod
    def _metrics(payload: dict[str, Any]) -> dict[str, float]:
        metrics: dict[str, float] = {}
        fans = _dict(payload.get("fans"))
        channels = [item for item in _list(fans.get("channels")) if isinstance(item, dict)]
        monitored = [item for item in channels if item.get("monitored") is True] or channels
        rpm = [value for item in monitored if (value := _number(item.get("rpm"))) is not None]
        pwm = [value for item in monitored if (value := _number(item.get("pwm"))) is not None and value > 0]
        if (value := _average(rpm)) is not None:
            metrics["fan.rpm"] = value
        if (value := _average(pwm)) is not None:
            metrics["fan.pwm"] = value

        storage = _dict(payload.get("storage"))
        drive_temperatures = []
        for item in _list(storage.get("temperatures")):
            if not isinstance(item, dict):
                continue
            value = _number(item.get("temperature_c", item.get("temp")))
            if value is not None:
                drive_temperatures.append(value)
        if drive_temperatures:
            metrics["drive.temperature_c"] = max(drive_temperatures)

        control = _dict(fans.get("control"))
        hottest = _number(control.get("thermal_hottest_temperature_c"))
        if hottest is not None:
            metrics["cpu.temperature_c"] = hottest

        primary = next(
            (item for item in _list(payload.get("network")) if isinstance(item, dict) and item.get("primary") is True),
            None,
        )
        if primary:
            speed = _number(primary.get("speed_mbps", primary.get("link_mbps")))
            errors = _number(primary.get("errors"))
            if speed is not None:
                metrics["network.link_mbps"] = speed
            if errors is not None:
                metrics["network.errors"] = errors
        return metrics

    @staticmethod
    def _hard_faults(cards: list[dict[str, Any]]) -> tuple[str, ...]:
        codes = {str(card.get("code") or "") for card in cards}
        hard = set()
        if "cooling.fan_stall" in codes:
            hard.add("fan.rpm")
        if "thermal.high_temperature" in codes:
            hard.update(("drive.temperature_c", "cpu.temperature_c"))
        if "network.link_down" in codes:
            hard.add("network.link_mbps")
        if codes & {"storage.smart_warning", "storage.disk_faulted"}:
            hard.add("drive.smart_reallocated")
        return tuple(hard)

    def observe(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._sequence += 1
        timestamp = _number(payload.get("timestamp"))
        if timestamp is None:
            timestamp = float(self._sequence)
        cards = [item for item in _list(payload.get("operator_guidance")) if isinstance(item, dict)]
        metrics = self._metrics(payload)
        outlook = self.oracle.observe(
            timestamp=timestamp,
            metrics=metrics,
            hard_faults=self._hard_faults(cards),
        )
        incident = correlate_incident(cards, outlook)
        return {
            "schema_version": 1,
            "project": "AEGIS",
            "read_only": True,
            "production_mutation": False,
            "state": "INCIDENT" if incident else outlook.get("state", "NORMAL"),
            "active_incident": incident,
            "oracle": outlook,
            "coverage_matrix": self.matrix,
            "coverage_summary": {
                "total": self.matrix["total"],
                "trusted": self.matrix["trusted"],
                "gaps": self.matrix["gaps"],
            },
        }


__all__ = ["AegisReliabilityEngine"]
