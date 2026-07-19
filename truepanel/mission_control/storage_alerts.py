"""
Metadata-driven storage alert presentation.

This module converts storage-health MissionEvents into concise 16x2 display
content. It does not create DisplayFrames or communicate with LCD hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .event import MissionEvent


LCD_WIDTH = 16


@dataclass(frozen=True)
class StorageAlertContent:
    line1: str
    line2: str


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default

    return str(value).strip()


def _integer(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fit(value: Any) -> str:
    return _text(value)[:LCD_WIDTH]


def _metadata(event: MissionEvent) -> Mapping[str, Any]:
    metadata = getattr(event, "metadata", {})

    if isinstance(metadata, Mapping):
        return metadata

    return {}


def _label(metadata: Mapping[str, Any]) -> str:
    label = _text(metadata.get("label"))

    if label:
        return label

    bay = _integer(metadata.get("physical_bay"))

    if bay is not None:
        return f"Bay {bay}"

    device = _text(metadata.get("device"))

    if device:
        return device

    return "Storage"


def _state_text(metadata: Mapping[str, Any]) -> str:
    state = _text(metadata.get("new_state")).lower()

    labels = {
        "healthy": "Healthy",
        "warning": "Warning",
        "critical": "Critical",
        "unknown": "Unknown",
    }

    return labels.get(state, state.title() if state else "")


def _counter_content(
    metadata: Mapping[str, Any],
) -> StorageAlertContent | None:
    """
    Return the most actionable SMART counter for the display.

    Pending and offline-uncorrectable sectors are prioritized because they
    indicate unreadable media. Reallocated sectors follow, then interface
    errors, which may indicate cabling or backplane trouble.
    """

    label = _label(metadata)

    counters = (
        ("pending_sectors", "PENDING SECTORS"),
        ("offline_uncorrectable", "UNCORRECTABLE"),
        ("reallocated_sectors", "REALLOCATED"),
        ("interface_errors", "LINK ERRORS"),
    )

    for field, title in counters:
        value = _integer(metadata.get(field))

        if value is not None and value > 0:
            return StorageAlertContent(
                line1=_fit(title),
                line2=_fit(f"{label} {value}"),
            )

    return None


def render_storage_alert(
    event: MissionEvent,
) -> StorageAlertContent | None:
    """
    Render a storage-health event.

    Return None when the event is not one of the structured events produced by
    StorageHealthWatcher. DisplayManager can then use its generic fallback.
    """

    metadata = _metadata(event)
    change_type = _text(metadata.get("change_type")).lower()

    if not change_type:
        return None

    label = _label(metadata)
    state = _state_text(metadata)

    if change_type == "operation_completed":
        operation = _text(
            metadata.get("operation"),
            "storage",
        ).upper()

        return StorageAlertContent(
            line1=_fit(f"{operation} DONE"),
            line2="POOL ONLINE",
        )

    if change_type == "operation_problem":
        operation = _text(
            metadata.get("operation"),
            "storage",
        ).upper()
        remaining = _text(metadata.get("remaining"))

        return StorageAlertContent(
            line1=_fit(f"{operation} ALERT"),
            line2=_fit(remaining or "CHECK POOL"),
        )

    if change_type == "device_missing":
        return StorageAlertContent(
            line1="DRIVE MISSING",
            line2=_fit(label),
        )

    if change_type == "device_inserted":
        detail = f"{label} {state or 'Detected'}"

        return StorageAlertContent(
            line1="NEW DRIVE",
            line2=_fit(detail),
        )

    if change_type == "recovered":
        return StorageAlertContent(
            line1="DRIVE RECOVERED",
            line2=_fit(f"{label} Healthy"),
        )

    if change_type == "temperature_increased":
        temperature = _integer(metadata.get("temperature_c"))
        detail = label

        if temperature is not None:
            detail = f"{label} {temperature} C"

        return StorageAlertContent(
            line1="DRIVE TEMP",
            line2=_fit(detail),
        )

    if change_type == "media_counter_increased":
        counter = _counter_content(metadata)

        if counter is not None:
            return counter

        return StorageAlertContent(
            line1="MEDIA ERRORS",
            line2=_fit(label),
        )

    if change_type in {
        "initial_condition",
        "state_changed",
        "health_degraded",
    }:
        counter = _counter_content(metadata)

        if counter is not None:
            return counter

        if state == "Critical":
            title = "DRIVE CRITICAL"
        elif state == "Warning":
            title = "DRIVE WARNING"
        else:
            title = event.title or "STORAGE ALERT"

        detail = f"{label} {state}".strip()

        return StorageAlertContent(
            line1=_fit(title),
            line2=_fit(detail),
        )

    return None


__all__ = [
    "StorageAlertContent",
    "render_storage_alert",
]
