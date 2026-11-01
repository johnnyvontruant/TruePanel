"""
Historical telemetry renderers for the TruePanel 16x2 LCD.

These renderers are registered through the Plugin API rather than being
hard-coded into DisplayManager.
"""

from __future__ import annotations

import time
from typing import Callable, Iterable

from truepanel.display.widgets import sparkline
from truepanel.history.service import HistoryService
from truepanel.mission_control.constants import Priority


LCD_WIDTH = 16


def history_settings(display_manager):
    history_config = display_manager.config.get("history", {})
    return history_config.get("lcd", {})


def history_service(display_manager):
    """
    Return one cached HistoryService per DisplayManager.

    This avoids rebuilding the service object on every LCD page refresh.
    """

    service = getattr(
        display_manager,
        "_history_lcd_service",
        None,
    )

    if service is None:
        config = display_manager.config.get("history", {})
        service = HistoryService(config)
        display_manager._history_lcd_service = service

    return service


def window_hours(display_manager):
    settings = history_settings(display_manager)

    try:
        return max(
            1.0 / 60.0,
            float(settings.get("window_hours", 1)),
        )
    except (TypeError, ValueError):
        return 1.0


def point_count(display_manager):
    settings = history_settings(display_manager)

    try:
        return max(
            4,
            min(
                LCD_WIDTH,
                int(settings.get("points", LCD_WIDTH)),
            ),
        )
    except (TypeError, ValueError):
        return LCD_WIDTH


def window_label(hours):
    if hours < 1:
        minutes = max(1, int(round(hours * 60)))
        return f"{minutes}M"

    if hours < 24:
        return f"{int(round(hours))}H"

    days = max(1, int(round(hours / 24)))
    return f"{days}D"


def get_samples(display_manager):
    hours = window_hours(display_manager)
    since = time.time() - (hours * 60 * 60)

    return history_service(display_manager).samples(
        since=since,
    )


def numeric(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def downsample_values(values: Iterable[float], points=16):
    values = [numeric(value) for value in values]
    points = max(1, int(points))

    if not values:
        return []

    if len(values) <= points:
        return values

    result = []
    bucket_size = len(values) / points

    for index in range(points):
        start = int(index * bucket_size)
        end = int((index + 1) * bucket_size)

        if end <= start:
            end = start + 1

        bucket = values[start:end]

        if bucket:
            result.append(sum(bucket) / len(bucket))

    return result


def empty_frame(display_manager, title):
    return display_manager.make_frame(
        line1=title,
        line2="Collecting Data",
        priority=Priority.INFO,
    )


def metric_frame(
    display_manager,
    title,
    values,
    formatter: Callable[[float], str],
):
    values = [numeric(value) for value in values]

    if not values:
        return empty_frame(display_manager, title)

    points = downsample_values(
        values,
        point_count(display_manager),
    )

    latest = values[-1]
    peak = max(values)
    label = window_label(window_hours(display_manager))

    latest_text = formatter(latest)
    peak_text = formatter(peak)

    line1 = f"{title} {label} N{latest_text} P{peak_text}"

    return display_manager.make_frame(
        line1=line1[:LCD_WIDTH],
        line2=sparkline(points, width=LCD_WIDTH),
        priority=Priority.INFO,
    )


def percent(value):
    return f"{value:.0f}%"


def temperature(value):
    return f"{value:.0f}C"


def count(value):
    return f"{value:.0f}"


def render_cpu_history(state, display_manager):
    samples = get_samples(display_manager)

    return metric_frame(
        display_manager,
        "CPU",
        [sample.cpu_percent for sample in samples],
        percent,
    )


def render_ram_history(state, display_manager):
    samples = get_samples(display_manager)

    return metric_frame(
        display_manager,
        "RAM",
        [sample.ram_percent for sample in samples],
        percent,
    )


def render_temperature_history(state, display_manager):
    samples = get_samples(display_manager)

    return metric_frame(
        display_manager,
        "TEMP",
        [sample.hottest_temp for sample in samples],
        temperature,
    )


def render_capacity_history(state, display_manager):
    samples = get_samples(display_manager)

    return metric_frame(
        display_manager,
        "POOL",
        [sample.pool_capacity for sample in samples],
        percent,
    )


def render_network_history(state, display_manager):
    samples = get_samples(display_manager)
    values = [
        sample.network_download + sample.network_upload
        for sample in samples
    ]

    return metric_frame(
        display_manager,
        "NET",
        values,
        display_manager.rate_text,
    )


def render_zfs_history(state, display_manager):
    samples = get_samples(display_manager)
    values = [
        sample.zfs_read + sample.zfs_write
        for sample in samples
    ]

    return metric_frame(
        display_manager,
        "ZFS",
        values,
        display_manager.rate_text,
    )


def render_alert_history_graph(state, display_manager):
    samples = get_samples(display_manager)

    return metric_frame(
        display_manager,
        "ALERT",
        [sample.alert_count for sample in samples],
        count,
    )


HISTORY_RENDERERS = {
    "history-cpu": render_cpu_history,
    "history-ram": render_ram_history,
    "history-temperature": render_temperature_history,
    "history-capacity": render_capacity_history,
    "history-network": render_network_history,
    "history-zfs": render_zfs_history,
    "history-alerts": render_alert_history_graph,
}
