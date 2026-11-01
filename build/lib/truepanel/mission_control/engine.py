from .constants import Category, Priority
from .event import MissionEvent


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
