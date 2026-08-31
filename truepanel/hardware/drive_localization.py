"""Read-only drive-to-bay localization for telemetry enrichment.

Several telemetry surfaces (Mission Control's storage temperatures, AEGIS's
incident evidence) have historically reported a hottest or faulted drive by
device name alone, with no indication of which physical bay holds it. This
module joins that device name against the same topology resolution Project
Lifeline and the front-bay LED mirror already use, so operators see a bay
number instead of a bare device name.

This module performs no hardware writes and invents no topology. A drive
whose device name cannot be resolved to a bay is left unresolved rather than
guessed, matching the project's existing rule that uncertainty must be
preserved rather than hidden.
"""

from __future__ import annotations

from typing import Any

_DEVICE_KEYS = ("device", "drive", "disk", "name")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _device_name(entry: dict[str, Any]) -> str:
    """Extract a bare device name (``sda``, not ``/dev/sda``) from an entry.

    Different collectors have historically used different field names for
    the same concept, so every known variant is checked in a stable order.
    """

    for key in _DEVICE_KEYS:
        value = _text(entry.get(key))
        if value:
            return value.rsplit("/", 1)[-1]
    return ""


def localize_drive_readings(
    readings: Any,
    device_bay_map: Any,
) -> list[Any]:
    """Attach a resolved physical bay to each drive reading, when known.

    Entries that already carry a non-``None`` ``bay`` value are left exactly
    as they are: a caller with a more specific or more authoritative bay
    source always wins over this generic join. Entries whose device cannot
    be resolved receive an explicit ``bay: None`` rather than a guessed or
    omitted field, so a consumer can distinguish "known to have no bay"
    from "bay not yet checked."

    Non-list input, non-dict entries, and a missing or empty device-bay map
    are all handled defensively; this function never raises on malformed
    telemetry, it simply localizes what it safely can.
    """

    if not isinstance(readings, list):
        return []

    mapping = device_bay_map if isinstance(device_bay_map, dict) else {}

    localized: list[Any] = []
    for entry in readings:
        if not isinstance(entry, dict):
            localized.append(entry)
            continue

        enriched = dict(entry)
        if enriched.get("bay") is None:
            device = _device_name(enriched)
            enriched["bay"] = mapping.get(device) if device else None
        localized.append(enriched)

    return localized


__all__ = ["localize_drive_readings"]
