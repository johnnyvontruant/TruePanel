"""
Reusable hardware experiments for Project Stargate.

Experiments operate on an A125Controller-compatible object and contain no
serial-port setup or command-line parsing. This makes them independently
testable with simulated controllers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from truepanel.lab.statistics import (
    LatencySummary,
    summarize_latencies,
)


SUPPORTED_REPEAT_QUERIES = (
    "board",
    "version",
    "buttons",
)


@dataclass(frozen=True)
class RepeatSample:
    index: int
    success: bool
    latency_ms: float
    value: int | None = None
    error: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "value": self.value,
            "value_hex": (
                f"0x{self.value:04X}"
                if self.value is not None
                else None
            ),
            "error": self.error,
        }


@dataclass
class RepeatExperimentResult:
    query: str
    requested_count: int
    interval_seconds: float
    samples: list[RepeatSample] = field(default_factory=list)

    @property
    def successful_samples(self) -> list[RepeatSample]:
        return [
            sample
            for sample in self.samples
            if sample.success
        ]

    @property
    def failed_samples(self) -> list[RepeatSample]:
        return [
            sample
            for sample in self.samples
            if not sample.success
        ]

    @property
    def successes(self) -> int:
        return len(self.successful_samples)

    @property
    def failures(self) -> int:
        return len(self.failed_samples)

    @property
    def success_rate(self) -> float:
        if not self.samples:
            return 0.0

        return (self.successes / len(self.samples)) * 100.0

    @property
    def latency(self) -> LatencySummary:
        return summarize_latencies(
            [
                sample.latency_ms
                for sample in self.successful_samples
            ]
        )

    @property
    def stable_value(self) -> int | None:
        values = {
            sample.value
            for sample in self.successful_samples
        }

        if len(values) == 1:
            return next(iter(values))

        return None

    @property
    def values_consistent(self) -> bool:
        values = [
            sample.value
            for sample in self.successful_samples
        ]

        return bool(values) and len(set(values)) == 1

    def as_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "requested_count": self.requested_count,
            "completed_count": len(self.samples),
            "interval_seconds": self.interval_seconds,
            "successes": self.successes,
            "failures": self.failures,
            "success_rate": self.success_rate,
            "values_consistent": self.values_consistent,
            "stable_value": self.stable_value,
            "stable_value_hex": (
                f"0x{self.stable_value:04X}"
                if self.stable_value is not None
                else None
            ),
            "latency": self.latency.as_dict(),
            "samples": [
                sample.as_dict()
                for sample in self.samples
            ],
        }


def resolve_query(controller, query: str) -> Callable[[], int]:
    """Resolve a safe, read-only query method."""

    methods = {
        "board": controller.query_board_id,
        "version": controller.query_protocol_version,
        "buttons": controller.query_buttons,
    }

    try:
        return methods[query]
    except KeyError as error:
        supported = ", ".join(SUPPORTED_REPEAT_QUERIES)
        raise ValueError(
            f"Unsupported repeat query {query!r}; "
            f"choose from: {supported}"
        ) from error


def run_repeat_experiment(
    controller,
    query: str,
    count: int = 25,
    interval: float = 0.10,
    sample_callback: Callable[[RepeatSample], None] | None = None,
) -> RepeatExperimentResult:
    """
    Repeatedly execute one safe A125 query and measure response latency.

    Individual failures are recorded rather than terminating the experiment.
    """

    count = int(count)
    interval = float(interval)

    if count < 1:
        raise ValueError("Repeat count must be at least 1")

    if interval < 0:
        raise ValueError("Repeat interval cannot be negative")

    query_method = resolve_query(controller, query)

    result = RepeatExperimentResult(
        query=query,
        requested_count=count,
        interval_seconds=interval,
    )

    for index in range(1, count + 1):
        started = time.perf_counter()

        try:
            value = int(query_method())
            elapsed_ms = (
                time.perf_counter() - started
            ) * 1000.0

            sample = RepeatSample(
                index=index,
                success=True,
                latency_ms=elapsed_ms,
                value=value,
            )
        except Exception as error:
            elapsed_ms = (
                time.perf_counter() - started
            ) * 1000.0

            sample = RepeatSample(
                index=index,
                success=False,
                latency_ms=elapsed_ms,
                error=f"{type(error).__name__}: {error}",
            )

        result.samples.append(sample)

        if sample_callback is not None:
            sample_callback(sample)

        if index < count and interval > 0:
            time.sleep(interval)

    return result
