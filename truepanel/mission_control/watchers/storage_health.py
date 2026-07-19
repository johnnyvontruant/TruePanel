"""
Mission Control integration for storage-health monitoring.

The storage-health implementation remains reusable under ``truepanel.watchers``.
This module owns production configuration and watcher construction for the
Mission Control runtime.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from truepanel.hardware.manager import HardwareManager
from truepanel.mission_control.storage_bay_indicator import (
    StorageBayIndicator,
)
from truepanel.watchers.storage_health import (
    StorageEventRecorder,
    StorageHealthChange,
    StorageHealthDiffer,
    StorageHealthWatcher,
)


DEFAULT_STORAGE_HEALTH_CONFIG = {
    "enabled": True,
    "interval": 300,
    "emit_initial_conditions": True,
    "record_events": True,
    "event_log": "/var/lib/truepanel/storage/events.jsonl",
    "bay_leds_enabled": False,
    "bay_leds_clear_on_start": True,
}


def get_storage_health_config(
    config: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Return storage-health configuration merged with production defaults.
    """

    settings = dict(DEFAULT_STORAGE_HEALTH_CONFIG)

    if not isinstance(config, Mapping):
        return settings

    mission_control = config.get("mission_control", {})

    if not isinstance(mission_control, Mapping):
        return settings

    overrides = mission_control.get("storage_health", {})

    if isinstance(overrides, Mapping):
        settings.update(overrides)

    return settings


def build_storage_health_watcher(
    config: Mapping[str, Any] | None,
    *,
    manager: HardwareManager | None = None,
    report_provider: Callable[[], Mapping[str, Any]] | None = None,
    clock: Callable[[], float] | None = None,
) -> StorageHealthWatcher | None:
    """
    Construct the configured production storage-health watcher.

    Returning ``None`` when disabled lets launchers register the watcher
    conditionally without teaching MissionControl about configuration.
    """

    settings = get_storage_health_config(config)

    if not bool(settings.get("enabled", True)):
        return None

    recorder = None

    if bool(settings.get("record_events", True)):
        event_log = settings.get(
            "event_log",
            DEFAULT_STORAGE_HEALTH_CONFIG["event_log"],
        )

        if event_log:
            recorder = StorageEventRecorder(str(event_log))

    event_observers = []

    if bool(settings.get("bay_leds_enabled", False)):
        manager = manager or HardwareManager()
        event_observers.append(
            StorageBayIndicator(
                manager.bay_leds,
                clear_on_start=bool(
                    settings.get(
                        "bay_leds_clear_on_start",
                        True,
                    )
                ),
            )
        )

    watcher_kwargs: dict[str, Any] = {
        "manager": manager,
        "report_provider": report_provider,
        "recorder": recorder,
        "event_observers": tuple(event_observers),
        "interval": float(settings.get("interval", 300)),
        "emit_initial_conditions": bool(
            settings.get("emit_initial_conditions", True)
        ),
    }

    if clock is not None:
        watcher_kwargs["clock"] = clock

    return StorageHealthWatcher(**watcher_kwargs)


__all__ = [
    "DEFAULT_STORAGE_HEALTH_CONFIG",
    "StorageEventRecorder",
    "StorageHealthChange",
    "StorageHealthDiffer",
    "StorageHealthWatcher",
    "build_storage_health_watcher",
    "get_storage_health_config",
]
