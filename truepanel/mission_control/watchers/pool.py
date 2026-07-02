"""
Pool Watcher

Monitors ZFS pool health and reports critical storage conditions.
"""

from ..constants import Category, Priority
from ..event import MissionEvent


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
