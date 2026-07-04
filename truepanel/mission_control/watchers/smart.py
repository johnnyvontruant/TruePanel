"""
SMART Watcher

Monitors SMART health and drive error counters reported by the collector.
"""

from ..constants import Category, Priority
from ..event import MissionEvent


def smart_watcher(state):
    smart = state.get("smart", [])

    if not smart:
        return None

    for drive in smart:
        name = drive.get("drive", "disk")
        health = drive.get("health", "UNKNOWN")
        pending = drive.get("pending", 0)
        offline = drive.get("offline_uncorrectable", 0)
        reallocated = drive.get("reallocated", 0)
        reported = drive.get("reported_uncorrect", 0)
        media = drive.get("media_errors", 0)
        critical_warning = drive.get("critical_warning", "0x00")

        if health == "FAILED":
            return MissionEvent(
                priority=Priority.CRITICAL,
                title="SMART FAIL",
                message=name,
                category=Category.STORAGE,
                timeout=15,
                event_id="smart.failed",
                source="smart_watcher",
            )

        if pending > 0:
            return MissionEvent(
                priority=Priority.CRITICAL,
                title="PENDING SECT",
                message=f"{name} {pending}",
                category=Category.STORAGE,
                timeout=15,
                event_id="smart.pending",
                source="smart_watcher",
            )

        if offline > 0:
            return MissionEvent(
                priority=Priority.CRITICAL,
                title="UNCORRECTABLE",
                message=f"{name} {offline}",
                category=Category.STORAGE,
                timeout=15,
                event_id="smart.offline_uncorrectable",
                source="smart_watcher",
            )

        if media > 0:
            return MissionEvent(
                priority=Priority.CRITICAL,
                title="MEDIA ERRORS",
                message=f"{name} {media}",
                category=Category.STORAGE,
                timeout=15,
                event_id="smart.media_errors",
                source="smart_watcher",
            )

        if critical_warning not in ["0x00", "0"]:
            return MissionEvent(
                priority=Priority.CRITICAL,
                title="NVME WARNING",
                message=f"{name} {critical_warning}",
                category=Category.STORAGE,
                timeout=15,
                event_id="smart.nvme_warning",
                source="smart_watcher",
            )

        if reallocated > 0:
            return MissionEvent(
                priority=Priority.WARNING,
                title="REALLOC SECT",
                message=f"{name} {reallocated}",
                category=Category.STORAGE,
                timeout=10,
                event_id="smart.reallocated",
                source="smart_watcher",
            )

        if reported > 0:
            return MissionEvent(
                priority=Priority.WARNING,
                title="SMART WARN",
                message=f"{name} {reported}",
                category=Category.STORAGE,
                timeout=10,
                event_id="smart.reported_uncorrect",
                source="smart_watcher",
            )

    return None
