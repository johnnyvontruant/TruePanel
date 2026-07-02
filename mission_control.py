from dataclasses import dataclass
from enum import Enum, IntEnum


MISSION_CONTROL_VERSION = "0.7.0-dev"


class Priority(IntEnum):
    NONE = 0
    HEALTHY = 10
    INFO = 40
    WARNING = 70
    CRITICAL = 100


class Category(str, Enum):
    HEALTH = "health"
    STORAGE = "storage"
    THERMAL = "thermal"
    NETWORK = "network"
    SYSTEM = "system"


@dataclass
class MissionEvent:
    priority: Priority
    title: str
    message: str
    category: Category = Category.SYSTEM
    timeout: int = 5
    event_id: str = "system.unknown"
    source: str = "mission_control"


class MissionControl:
    def __init__(self):
        self.watchers = []

    def register(self, watcher):
        self.watchers.append(watcher)

    def evaluate(self, state):
        events = []

        for watcher in self.watchers:
            event = watcher(state)
            if event:
                events.append(event)

        if not events:
            return MissionEvent(
                priority=Priority.NONE,
                title="TruePanel",
                message="No Status",
                category=Category.SYSTEM,
                event_id="system.none",
                source="mission_control",
            )

        return max(events, key=lambda event: event.priority)


def pool_watcher(state):
    pools = state.get("pools", [])

    if not pools:
        return None

    for pool in pools:
        if pool.get("health") != "ONLINE":
            return MissionEvent(
                priority=Priority.CRITICAL,
                title="POOL ALERT",
                message=f'{pool["name"]} {pool["health"]}',
                category=Category.STORAGE,
                timeout=15,
                event_id="storage.pool_alert",
                source="pool_watcher",
            )

    return None


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


def healthy_watcher(state):
    return MissionEvent(
        priority=Priority.HEALTHY,
        title="BattleStation",
        message="Healthy",
        category=Category.HEALTH,
        timeout=5,
        event_id="health.healthy",
        source="healthy_watcher",
    )


if __name__ == "__main__":
    mc = MissionControl()

    mc.register(pool_watcher)
    mc.register(thermal_watcher)
    mc.register(zfs_watcher)
    mc.register(healthy_watcher)

    event = mc.evaluate({
        "pools": [
            {"name": "tank", "health": "ONLINE"}
        ],
        "temps": [
            {"drive": "sda", "temp": 37},
            {"drive": "nvme0n1", "temp": 44}
        ],
        "zfs_activity": {
            "scrub_running": True,
            "resilver_running": False,
            "percent": 42,
            "remaining": None,
            "problem": False,
        }
    })

    print(event)
