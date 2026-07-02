"""
ZFS Watcher

Monitors scrub and resilver activity reported by the collector.
"""

from ..constants import Category, Priority
from ..event import MissionEvent


def zfs_watcher(state):
    activity = state.get("zfs_activity", {})

    if not activity:
        return None

    percent = activity.get("percent")
    percent_text = f"{percent}%" if percent is not None else "Running"

    if activity.get("resilver_running"):
        return MissionEvent(
            priority=Priority.INFO,
            title="RESILVER",
            message=percent_text,
            category=Category.STORAGE,
            timeout=10,
            event_id="storage.resilver",
            source="zfs_watcher",
        )

    if activity.get("scrub_running"):
        return MissionEvent(
            priority=Priority.INFO,
            title="SCRUB",
            message=percent_text,
            category=Category.STORAGE,
            timeout=10,
            event_id="storage.scrub",
            source="zfs_watcher",
        )

    return None
