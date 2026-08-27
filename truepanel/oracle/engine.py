"""Experimental predictive health intelligence for TruePanel Project ORACLE.

ORACLE intentionally remains read-only.  It learns a conservative baseline for
telemetry signals, highlights statistically unusual drift, and correlates
multiple weak signals without replacing TruePanel's existing hard-fault
watchers.  A statistical anomaly can become WATCH or DEVELOPING; only an
independently supplied hard-fault signal may produce FAULT.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from enum import Enum
from statistics import fmean, pstdev
from typing import Iterable, Mapping


class OracleState(str, Enum):
    """Project ORACLE outlook states."""

    NORMAL = "NORMAL"
    WATCH = "WATCH"
    DEVELOPING = "DEVELOPING"
    FAULT = "FAULT"


_SEVERITY = {
    OracleState.NORMAL: 0,
    OracleState.WATCH: 1,
    OracleState.DEVELOPING: 2,
    OracleState.FAULT: 3,
}


@dataclass(frozen=True)
class MetricSpec:
    """Describe how a telemetry signal becomes concerning."""

    key: str
    label: str
    direction: str = "both"
    unit: str = ""
    watch_relative: float = 0.08
    developing_relative: float = 0.15
    watch_z: float = 2.0
    developing_z: float = 3.0
    reference_floor: float = 1.0

    def __post_init__(self) -> None:
        if self.direction not in {"high", "low", "both"}:
            raise ValueError("metric direction must be high, low, or both")
        if self.reference_floor <= 0:
            raise ValueError("metric reference_floor must be positive")


@dataclass(frozen=True)
class CorrelationRule:
    """Promote several weak signals into a stronger developing condition."""

    key: str
    label: str
    signals: tuple[str, ...]
    summary: str
    minimum_matches: int | None = None

    @property
    def required_matches(self) -> int:
        return self.minimum_matches or len(self.signals)


DEFAULT_METRICS = (
    MetricSpec("fan.pwm", "Fan effort", "high", "%", reference_floor=100.0),
    MetricSpec("fan.rpm", "Fan speed", "low", "RPM", reference_floor=500.0),
    MetricSpec(
        "drive.temperature_c",
        "Drive temperature",
        "high",
        "C",
        watch_relative=0.06,
        developing_relative=0.12,
        reference_floor=20.0,
    ),
    MetricSpec(
        "drive.latency_ms",
        "Drive latency",
        "high",
        "ms",
        reference_floor=5.0,
    ),
    MetricSpec(
        "drive.smart_reallocated",
        "Reallocated sectors",
        "high",
        "sectors",
        watch_relative=0.05,
        developing_relative=0.15,
        reference_floor=100.0,
    ),
    MetricSpec(
        "cpu.temperature_c",
        "CPU temperature",
        "high",
        "C",
        reference_floor=25.0,
    ),
    MetricSpec(
        "network.link_mbps",
        "Negotiated link speed",
        "low",
        "Mbps",
        watch_relative=0.25,
        developing_relative=0.50,
        reference_floor=100.0,
    ),
    MetricSpec(
        "network.errors",
        "Network error count",
        "high",
        "errors",
        watch_relative=0.05,
        developing_relative=0.15,
        reference_floor=100.0,
    ),
)


DEFAULT_CORRELATIONS = (
    CorrelationRule(
        key="cooling.efficiency",
        label="Cooling efficiency degradation",
        signals=("fan.pwm", "fan.rpm"),
        summary="Fan effort is rising while delivered fan speed is falling.",
    ),
    CorrelationRule(
        key="chassis.airflow",
        label="Chassis airflow degradation",
        signals=("fan.rpm", "drive.temperature_c"),
        summary="Reduced fan performance is coinciding with rising drive temperature.",
    ),
    CorrelationRule(
        key="storage.media",
        label="Developing storage degradation",
        signals=(
            "drive.latency_ms",
            "drive.temperature_c",
            "drive.smart_reallocated",
        ),
        minimum_matches=2,
        summary="Multiple storage signals are drifting away from their learned baseline.",
    ),
    CorrelationRule(
        key="network.path",
        label="Network path degradation",
        signals=("network.link_mbps", "network.errors"),
        summary="Link quality and negotiated performance are degrading together.",
    ),
)


def _linear_slope(values: Iterable[float]) -> float:
    series = tuple(values)
    count = len(series)
    if count < 2:
        return 0.0

    x_mean = (count - 1) / 2.0
    y_mean = fmean(series)
    numerator = sum(
        (index - x_mean) * (value - y_mean)
        for index, value in enumerate(series)
    )
    denominator = sum(
        (index - x_mean) ** 2
        for index in range(count)
    )
    return numerator / denominator if denominator else 0.0


class _MetricTracker:
    def __init__(
        self,
        spec: MetricSpec,
        *,
        baseline_samples: int,
        baseline_window: int,
        trend_window: int,
    ) -> None:
        self.spec = spec
        self.baseline_samples = baseline_samples
        self.baseline = deque(maxlen=baseline_window)
        self.recent = deque(maxlen=trend_window)

    def observe(self, value: float, *, hard_fault: bool = False) -> dict:
        if not math.isfinite(value):
            raise ValueError(f"non-finite ORACLE telemetry for {self.spec.key}")

        self.recent.append(value)
        if len(self.baseline) < self.baseline_samples:
            self.baseline.append(value)
            return self._result(
                value=value,
                mean=fmean(self.baseline),
                stdev=pstdev(self.baseline) if len(self.baseline) > 1 else 0.0,
                state=OracleState.FAULT if hard_fault else OracleState.NORMAL,
                z_score=0.0,
                relative_delta=0.0,
                trend=_linear_slope(self.recent),
                confidence=len(self.baseline) / self.baseline_samples,
            )

        mean = fmean(self.baseline)
        stdev = pstdev(self.baseline) if len(self.baseline) > 1 else 0.0
        reference = max(abs(mean), self.spec.reference_floor)
        scale = max(stdev, reference * 0.01)
        raw_delta = value - mean

        if self.spec.direction == "high":
            concerning_delta = max(0.0, raw_delta)
        elif self.spec.direction == "low":
            concerning_delta = max(0.0, -raw_delta)
        else:
            concerning_delta = abs(raw_delta)

        z_score = concerning_delta / scale
        relative_delta = concerning_delta / reference

        if hard_fault:
            state = OracleState.FAULT
        elif (
            z_score >= self.spec.developing_z
            and relative_delta >= self.spec.developing_relative
        ):
            state = OracleState.DEVELOPING
        elif (
            z_score >= self.spec.watch_z
            and relative_delta >= self.spec.watch_relative
        ):
            state = OracleState.WATCH
        else:
            state = OracleState.NORMAL

        # Do not teach an active anomaly back into the baseline.  Normal
        # observations continue adapting slowly through the bounded window.
        if state is OracleState.NORMAL:
            self.baseline.append(value)

        return self._result(
            value=value,
            mean=mean,
            stdev=stdev,
            state=state,
            z_score=z_score,
            relative_delta=relative_delta,
            trend=_linear_slope(self.recent),
            confidence=1.0,
        )

    def _result(
        self,
        *,
        value: float,
        mean: float,
        stdev: float,
        state: OracleState,
        z_score: float,
        relative_delta: float,
        trend: float,
        confidence: float,
    ) -> dict:
        return {
            "key": self.spec.key,
            "label": self.spec.label,
            "unit": self.spec.unit,
            "state": state.value,
            "value": round(value, 6),
            "baseline_mean": round(mean, 6),
            "baseline_stdev": round(stdev, 6),
            "z_score": round(z_score, 3),
            "relative_delta": round(relative_delta, 6),
            "trend_per_sample": round(trend, 6),
            "confidence": round(max(0.0, min(1.0, confidence)), 3),
            "baseline_samples": len(self.baseline),
        }


class OracleEngine:
    """Learn normal behavior and identify developing telemetry anomalies."""

    def __init__(
        self,
        *,
        metric_specs: Iterable[MetricSpec] = DEFAULT_METRICS,
        correlations: Iterable[CorrelationRule] = DEFAULT_CORRELATIONS,
        baseline_samples: int = 12,
        baseline_window: int = 120,
        trend_window: int = 6,
    ) -> None:
        if baseline_samples < 3:
            raise ValueError("ORACLE baseline_samples must be at least 3")
        if baseline_window < baseline_samples:
            raise ValueError("ORACLE baseline_window cannot be smaller than warmup")
        if trend_window < 2:
            raise ValueError("ORACLE trend_window must be at least 2")

        specs = tuple(metric_specs)
        self.specs = {spec.key: spec for spec in specs}
        self.correlations = tuple(correlations)
        self.trackers = {
            spec.key: _MetricTracker(
                spec,
                baseline_samples=baseline_samples,
                baseline_window=baseline_window,
                trend_window=trend_window,
            )
            for spec in specs
        }

    def observe(
        self,
        *,
        timestamp: float,
        metrics: Mapping[str, float | int],
        hard_faults: Iterable[str] = (),
    ) -> dict:
        """Observe one telemetry frame and return a Mission-Control-ready outlook."""

        if not math.isfinite(float(timestamp)):
            raise ValueError("ORACLE timestamp must be finite")

        hard_fault_keys = set(hard_faults)
        metric_results: dict[str, dict] = {}
        for key, tracker in self.trackers.items():
            if key not in metrics:
                continue
            value = float(metrics[key])
            metric_results[key] = tracker.observe(
                value,
                hard_fault=key in hard_fault_keys,
            )

        correlations = self._correlate(metric_results)
        states = [
            OracleState(result["state"])
            for result in metric_results.values()
        ]
        states.extend(
            OracleState(result["state"])
            for result in correlations
        )
        overall = max(states, key=_SEVERITY.get) if states else OracleState.NORMAL

        confidences = [
            float(result.get("confidence", 0.0))
            for result in metric_results.values()
        ]
        confidence = fmean(confidences) if confidences else 0.0
        active = [
            result
            for result in metric_results.values()
            if result["state"] != OracleState.NORMAL.value
        ]

        return {
            "schema_version": 1,
            "experimental": True,
            "read_only": True,
            "predictive_authority": False,
            "timestamp": float(timestamp),
            "state": overall.value,
            "confidence": round(confidence, 3),
            "summary": self._summary(overall, active, correlations),
            "metrics": metric_results,
            "correlations": correlations,
            "active_signals": [result["key"] for result in active],
        }

    def _correlate(self, metric_results: Mapping[str, dict]) -> list[dict]:
        results = []
        for rule in self.correlations:
            matched = [
                key
                for key in rule.signals
                if key in metric_results
                and _SEVERITY[OracleState(metric_results[key]["state"])]
                >= _SEVERITY[OracleState.WATCH]
            ]
            if len(matched) < rule.required_matches:
                continue

            state = OracleState.DEVELOPING
            if any(
                metric_results[key]["state"] == OracleState.FAULT.value
                for key in matched
            ):
                state = OracleState.FAULT

            results.append(
                {
                    "key": rule.key,
                    "label": rule.label,
                    "state": state.value,
                    "summary": rule.summary,
                    "signals": matched,
                    "required_matches": rule.required_matches,
                }
            )
        return results

    @staticmethod
    def _summary(
        state: OracleState,
        active: list[dict],
        correlations: list[dict],
    ) -> str:
        if state is OracleState.NORMAL:
            return "Learned behavior is within the current normal envelope."
        if state is OracleState.FAULT:
            return "A hard fault is present; defer to TruePanel's verified fault guidance."
        if correlations:
            return correlations[0]["summary"]
        if active:
            label = str(active[0].get("label") or active[0].get("key"))
            return f"{label} is drifting away from its learned baseline."
        return "Developing behavior requires observation."
