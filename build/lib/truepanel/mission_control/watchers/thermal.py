"""
Thermal Watcher

Monitors drive temperatures and reports hot or critical drives.
"""

from ..constants import Category, Priority
from ..event import MissionEvent


def thermal_watcher(state):
    temps = state.get("temps", [])

    if not temps:
        return None

    hottest = max(temps, key=lambda drive: drive.get("temp", 0))
    drive = hottest.get("drive", "disk")
    temp = hottest.get("temp", 0)

    if temp >= 55:
        return MissionEvent(
            priority=Priority.CRITICAL,
            title="CRITICAL TEMP",
            message=f"{drive} {temp}C",
            category=Category.THERMAL,
            timeout=15,
            event_id="thermal.critical",
            source="thermal_watcher",
        )

    if temp >= 50:
        return MissionEvent(
            priority=Priority.WARNING,
            title="HOT DRIVE",
            message=f"{drive} {temp}C",
            category=Category.THERMAL,
            timeout=10,
            event_id="thermal.hot",
            source="thermal_watcher",
        )

    return None
