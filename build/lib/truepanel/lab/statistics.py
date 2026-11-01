"""
Statistical helpers for Project Stargate experiments.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class LatencySummary:
    """Summary statistics for a collection of latency measurements."""

    count: int
    minimum_ms: float | None = None
    maximum_ms: float | None = None
    average_ms: float | None = None
    median_ms: float | None = None
    p95_ms: float | None = None

    def as_dict(self) -> dict[str, int | float | None]:
        return {
            "count": self.count,
            "minimum_ms": self.minimum_ms,
            "maximum_ms": self.maximum_ms,
            "average_ms": self.average_ms,
            "median_ms": self.median_ms,
            "p95_ms": self.p95_ms,
        }


def percentile_nearest_rank(
    values: list[float],
    percentile: float,
) -> float | None:
    """
    Return a percentile using the nearest-rank method.

    The percentile must be between 0 and 100, inclusive.
    """

    if not values:
        return None

    if not 0 <= percentile <= 100:
        raise ValueError("Percentile must be between 0 and 100")

    ordered = sorted(float(value) for value in values)

    if percentile == 0:
        return ordered[0]

    rank = math.ceil((percentile / 100.0) * len(ordered))
    index = max(0, min(len(ordered) - 1, rank - 1))

    return ordered[index]


def summarize_latencies(
    values_ms: list[float],
) -> LatencySummary:
    """Calculate latency statistics in milliseconds."""

    if not values_ms:
        return LatencySummary(count=0)

    values = [float(value) for value in values_ms]

    return LatencySummary(
        count=len(values),
        minimum_ms=min(values),
        maximum_ms=max(values),
        average_ms=statistics.fmean(values),
        median_ms=statistics.median(values),
        p95_ms=percentile_nearest_rank(values, 95),
    )
