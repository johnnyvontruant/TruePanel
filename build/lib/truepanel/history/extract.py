"""
Convert TruePanel collector state into compact historical samples.
"""

from __future__ import annotations

import time
from typing import Any

from .models import TelemetrySample


def numeric(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def integer(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return int(default)


def capacity_percent(value: Any) -> float:
    if isinstance(value, str):
        value = value.strip().rstrip("%")

    return numeric(value)


def hottest_temperature(state: dict[str, Any]):
    temps = state.get("temps", []) or []

    if not temps:
        return 0.0, ""

    hottest = max(
        temps,
        key=lambda item: numeric(item.get("temp", 0)),
    )

    return (
        numeric(hottest.get("temp", 0)),
        str(hottest.get("drive", "")),
    )


def fullest_pool(state: dict[str, Any]):
    pools = state.get("pools", []) or []

    if not pools:
        return 0.0, "", "UNKNOWN"

    pool = max(
        pools,
        key=lambda item: capacity_percent(
            item.get("capacity", 0)
        ),
    )

    return (
        capacity_percent(pool.get("capacity", 0)),
        str(pool.get("name", "")),
        str(pool.get("health", "UNKNOWN")),
    )


def network_rates(state: dict[str, Any]):
    network = state.get("network", {}) or {}

    direct_download = (
        network.get("download_bytes_per_sec")
        or network.get("rx_bytes_per_sec")
        or network.get("rx_rate")
    )

    direct_upload = (
        network.get("upload_bytes_per_sec")
        or network.get("tx_bytes_per_sec")
        or network.get("tx_rate")
    )

    if direct_download is not None or direct_upload is not None:
        return (
            numeric(direct_download),
            numeric(direct_upload),
        )

    download = 0.0
    upload = 0.0

    for interface in network.values():
        if not isinstance(interface, dict):
            continue

        if "download_mb" in interface:
            download += numeric(interface.get("download_mb")) * 1024 * 1024
        else:
            download += numeric(
                interface.get(
                    "download_bytes_per_sec",
                    interface.get(
                        "rx_bytes_per_sec",
                        interface.get("rx_rate", 0),
                    ),
                )
            )

        if "upload_mb" in interface:
            upload += numeric(interface.get("upload_mb")) * 1024 * 1024
        else:
            upload += numeric(
                interface.get(
                    "upload_bytes_per_sec",
                    interface.get(
                        "tx_bytes_per_sec",
                        interface.get("tx_rate", 0),
                    ),
                )
            )

    return download, upload


def zfs_rates(state: dict[str, Any]):
    activity = state.get("zfs_activity", {}) or {}

    read_rate = numeric(
        activity.get(
            "read_bytes_per_sec",
            activity.get("read_rate", 0),
        )
    )

    write_rate = numeric(
        activity.get(
            "write_bytes_per_sec",
            activity.get("write_rate", 0),
        )
    )

    return read_rate, write_rate


def smart_problem_count(state: dict[str, Any]) -> int:
    count = 0

    for drive in state.get("smart", []) or []:
        if str(drive.get("health", "")).upper() == "FAILED":
            count += 1
            continue

        if numeric(drive.get("pending", 0)) > 0:
            count += 1
            continue

        if numeric(drive.get("offline_uncorrectable", 0)) > 0:
            count += 1
            continue

        if numeric(drive.get("media_errors", 0)) > 0:
            count += 1
            continue

        if str(
            drive.get("critical_warning", "0x00")
        ).lower() not in ("0", "0x00", ""):
            count += 1

    return count


def sample_from_state(
    state: dict[str, Any],
    alert_count: int = 0,
    timestamp: float | None = None,
) -> TelemetrySample:
    hottest_temp, hottest_drive = hottest_temperature(state)
    pool_capacity, pool_name, pool_health = fullest_pool(state)
    network_download, network_upload = network_rates(state)
    zfs_read, zfs_write = zfs_rates(state)

    activity = state.get("zfs_activity", {}) or {}
    zfs_percent = activity.get("percent")

    if zfs_percent is not None:
        zfs_percent = numeric(zfs_percent)

    return TelemetrySample(
        timestamp=float(timestamp or time.time()),
        hostname=str(state.get("hostname", "unknown")),
        cpu_percent=numeric(state.get("cpu_percent", 0)),
        ram_percent=numeric(state.get("ram_percent", 0)),
        hottest_temp=hottest_temp,
        hottest_drive=hottest_drive,
        pool_capacity=pool_capacity,
        pool_name=pool_name,
        pool_health=pool_health,
        network_download=network_download,
        network_upload=network_upload,
        zfs_read=zfs_read,
        zfs_write=zfs_write,
        scrub_running=bool(activity.get("scrub_running", False)),
        resilver_running=bool(
            activity.get("resilver_running", False)
        ),
        zfs_percent=zfs_percent,
        smart_problem_count=smart_problem_count(state),
        alert_count=integer(alert_count),
    )
