"""Mission Control composition service for Project AEGIS."""

from __future__ import annotations

import math
from copy import deepcopy
from statistics import fmean
from threading import Lock
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
    """Add predictive outlook, incident correlation, and coverage evidence.

    Mission Control is a threaded HTTP service and several dashboard surfaces
    may read the same status endpoint. ORACLE therefore samples on a bounded
    telemetry cadence rather than once per browser request. Correlation still
    re-evaluates every request so a verified hard alert is presented
    immediately without training duplicate reads into the learned baseline.
    """

    def __init__(
        self,
        *,
        oracle: OracleEngine | None = None,
        sample_interval_seconds: float = 5.0,
    ) -> None:
        interval = _number(sample_interval_seconds)
        if interval is None or interval <= 0:
            raise ValueError("AEGIS sample interval must be finite and positive")

        self.oracle = oracle or OracleEngine()
        self.sample_interval_seconds = interval
        self.rehearsals = rehearse_recovery_paths()
        self.matrix = coverage_matrix(self.rehearsals)
        self._sequence = 0
        self._last_sample_timestamp: float | None = None
        self._last_outlook: dict[str, Any] | None = None
        self._sample_lock = Lock()

    @staticmethod
    def _metrics(payload: dict[str, Any]) -> dict[str, float]:
        metrics: dict[str, float] = {}
        fans = _dict(payload.get("fans"))
        channels = [item for item in _list(fans.get("channels")) if isinstance(item, dict)]
        monitored = [item for item in channels if item.get("monitored") is True] or channels
        rpm = [value for item in monitored if (value := _number(item.get("rpm"))) is not None]
        pwm = [
            value
            for item in monitored
            if (value := _number(item.get("pwm"))) is not None and value > 0
        ]
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

        reallocated = []
        for item in _list(storage.get("smart")):
            if not isinstance(item, dict):
                continue
            value = _number(item.get("reallocated"))
            if value is not None:
                reallocated.append(value)
        if reallocated:
            metrics["drive.smart_reallocated"] = max(reallocated)

        control = _dict(fans.get("control"))
        hottest = _number(control.get("thermal_hottest_temperature_c"))
        if hottest is not None:
            metrics["cpu.temperature_c"] = hottest

        primary = next(
            (
                item
                for item in _list(payload.get("network"))
                if isinstance(item, dict) and item.get("primary") is True
            ),
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

    def _observe_oracle(
        self,
        *,
        source_timestamp: float | None,
        metrics: dict[str, float],
        hard_faults: tuple[str, ...],
    ) -> tuple[dict[str, Any], float, bool]:
        with self._sample_lock:
            self._sequence += 1
            timestamp = source_timestamp
            if timestamp is None:
                if self._last_sample_timestamp is None:
                    timestamp = float(self._sequence) * self.sample_interval_seconds
                else:
                    timestamp = (
                        self._last_sample_timestamp + self.sample_interval_seconds
                    )

            fresh = (
                self._last_outlook is None
                or self._last_sample_timestamp is None
                or timestamp - self._last_sample_timestamp
                >= self.sample_interval_seconds
            )
            if fresh:
                self._last_outlook = self.oracle.observe(
                    timestamp=timestamp,
                    metrics=metrics,
                    hard_faults=hard_faults,
                )
                self._last_sample_timestamp = timestamp

            return (
                deepcopy(self._last_outlook or {}),
                float(self._last_sample_timestamp or timestamp),
                fresh,
            )

    def observe(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_timestamp = _number(payload.get("timestamp"))
        cards = [
            item
            for item in _list(payload.get("operator_guidance"))
            if isinstance(item, dict)
        ]
        metrics = self._metrics(payload)
        outlook, sampled_at, fresh = self._observe_oracle(
            source_timestamp=source_timestamp,
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
            "sampling": {
                "sampled_at": sampled_at,
                "source_timestamp": source_timestamp,
                "fresh_sample": fresh,
                "minimum_interval_seconds": self.sample_interval_seconds,
                "request_count": self._sequence,
            },
            "coverage_matrix": self.matrix,
            "coverage_summary": {
                "total": self.matrix["total"],
                "trusted": self.matrix["trusted"],
                "gaps": self.matrix["gaps"],
            },
        }


__all__ = ["AegisReliabilityEngine"]
