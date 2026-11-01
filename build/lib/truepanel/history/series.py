"""
Historical telemetry series and aggregation helpers.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean


METRICS = {
    "cpu": "cpu_percent",
    "ram": "ram_percent",
    "temperature": "hottest_temp",
    "capacity": "pool_capacity",
    "download": "network_download",
    "upload": "network_upload",
    "zfs-read": "zfs_read",
    "zfs-write": "zfs_write",
    "smart-problems": "smart_problem_count",
    "alerts": "alert_count",
}


def metric_values(samples, metric):
    field = METRICS.get(metric, metric)

    return [
        getattr(sample, field)
        for sample in samples
        if hasattr(sample, field)
    ]


def downsample(samples, points=16, metric="cpu"):
    samples = list(samples)
    points = max(1, int(points))

    if not samples:
        return []

    values = metric_values(samples, metric)

    if len(values) <= points:
        return values

    bucket_size = len(values) / points
    result = []

    for index in range(points):
        start = int(index * bucket_size)
        end = int((index + 1) * bucket_size)

        if end <= start:
            end = start + 1

        bucket = values[start:end]

        if bucket:
            result.append(mean(bucket))

    return result


def summary(samples):
    samples = list(samples)

    if not samples:
        return {}

    result = {
        "samples": len(samples),
        "first_timestamp": samples[0].timestamp,
        "last_timestamp": samples[-1].timestamp,
    }

    for metric, field in METRICS.items():
        values = [
            float(getattr(sample, field))
            for sample in samples
        ]

        result[metric] = {
            "minimum": min(values),
            "maximum": max(values),
            "average": mean(values),
            "latest": values[-1],
        }

    return result


def bucket_by_hour(samples):
    buckets = defaultdict(list)

    for sample in samples:
        hour = int(sample.timestamp // 3600) * 3600
        buckets[hour].append(sample)

    return buckets
