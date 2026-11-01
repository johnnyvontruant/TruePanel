from ..constants import Category, Priority
from ..event import MissionEvent


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
