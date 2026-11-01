"""
Project Stargate Display Timing Laboratory.

Measures host-side execution latency for documented A125 display commands.
These measurements represent command encoding and serial transmission time,
not confirmed LCD processing time, because display writes do not return a
completion acknowledgment.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from truepanel.lab.statistics import (
    LatencySummary,
    summarize_latencies,
)


@dataclass(frozen=True)
class DisplayTimingSample:
    """One measured display-command execution."""

    index: int
    operation: str
    latency_ms: float
    success: bool
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "operation": self.operation,
            "latency_ms": self.latency_ms,
            "success": self.success,
            "detail": self.detail,
        }


@dataclass
class DisplayTimingResult:
    """Aggregate timing results for one display operation."""

    operation: str
    requested_count: int
    samples: list[DisplayTimingSample] = field(default_factory=list)

    @property
    def successes(self) -> int:
        return sum(sample.success for sample in self.samples)

    @property
    def failures(self) -> int:
        return sum(not sample.success for sample in self.samples)

    @property
    def healthy(self) -> bool:
        return (
            len(self.samples) == self.requested_count
            and self.failures == 0
        )

    @property
    def latency(self) -> LatencySummary:
        return summarize_latencies(
            [
                sample.latency_ms
                for sample in self.samples
                if sample.success
            ]
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "requested_count": self.requested_count,
            "successes": self.successes,
            "failures": self.failures,
            "healthy": self.healthy,
            "latency": self.latency.as_dict(),
            "samples": [
                sample.as_dict()
                for sample in self.samples
            ],
        }


def measure_display_operation(
    *,
    operation: str,
    execute: Callable[[], object],
    count: int = 25,
    interval: float = 0.0,
    clock: Callable[[], float] = time.perf_counter,
    sleep: Callable[[float], None] = time.sleep,
    callback: Callable[[DisplayTimingSample], None] | None = None,
) -> DisplayTimingResult:
    """Measure repeated host-side execution of one display operation."""

    operation = operation.strip()

    if not operation:
        raise ValueError("operation must not be empty")

    if count < 1:
        raise ValueError("count must be at least 1")

    if interval < 0:
        raise ValueError("interval must be non-negative")

    result = DisplayTimingResult(
        operation=operation,
        requested_count=count,
    )

    for index in range(1, count + 1):
        started = clock()

        try:
            execute()
            success = True
            detail = ""
        except Exception as error:
            success = False
            detail = str(error)

        latency_ms = (clock() - started) * 1000.0

        sample = DisplayTimingSample(
            index=index,
            operation=operation,
            latency_ms=latency_ms,
            success=success,
            detail=detail,
        )

        result.samples.append(sample)

        if callback is not None:
            callback(sample)

        if interval and index < count:
            sleep(interval)

    return result


def measure_clear(
    controller,
    *,
    count: int = 25,
    interval: float = 0.0,
    **kwargs,
) -> DisplayTimingResult:
    """Measure documented display-clear transmission latency."""

    return measure_display_operation(
        operation="clear",
        execute=controller.clear,
        count=count,
        interval=interval,
        **kwargs,
    )


def measure_line_write(
    controller,
    *,
    row: int,
    text: str,
    count: int = 25,
    interval: float = 0.0,
    **kwargs,
) -> DisplayTimingResult:
    """Measure one documented row-write operation."""

    if row not in (0, 1):
        raise ValueError("row must be 0 or 1")

    return measure_display_operation(
        operation=f"write-row-{row}",
        execute=lambda: controller.write_text(row, text),
        count=count,
        interval=interval,
        **kwargs,
    )


def measure_frame_write(
    controller,
    *,
    line1: str,
    line2: str,
    count: int = 25,
    interval: float = 0.0,
    **kwargs,
) -> DisplayTimingResult:
    """Measure a complete two-row frame transmission."""

    return measure_display_operation(
        operation="write-frame",
        execute=lambda: controller.write_frame(line1, line2),
        count=count,
        interval=interval,
        **kwargs,
    )
