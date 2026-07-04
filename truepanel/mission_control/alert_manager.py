"""
Alert Manager

Tracks MissionEvent alert state, suppresses duplicate alerts, stores alert
history, and decides whether an event should interrupt normal display flow.
"""

import time
from collections import deque
from dataclasses import dataclass
from enum import Enum

from .constants import Priority


class AlertState(Enum):
    NEW = "new"
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


@dataclass
class AlertDecision:
    interrupt: bool
    timeout: int
    event: object
    state: AlertState = AlertState.ACTIVE


class AlertManager:
    def __init__(self, interrupt_priority=Priority.WARNING, history_size=25):
        self.interrupt_priority = interrupt_priority
        self.last_event_id = None
        self.last_event_message = None
        self.last_event_time = 0
        self.history = deque(maxlen=history_size)

    def is_alert(self, event):
        return event.priority >= self.interrupt_priority

    def cooldown_expired(self, event):
        now = time.time()

        same_event = (
            event.event_id == self.last_event_id
            and event.message == self.last_event_message
        )

        if same_event and now - self.last_event_time < event.timeout:
            return False

        return True

    def record(self, event):
        if not self.is_alert(event):
            return False

        if self.history:
            last = self.history[0]

            if last.event_id == event.event_id and last.message == event.message:
                return False

        self.history.appendleft(event)
        return True

    def evaluate(self, event):
        if not self.is_alert(event):
            return AlertDecision(
                interrupt=False,
                timeout=event.timeout,
                event=event,
                state=AlertState.RESOLVED,
            )

        self.record(event)

        if not self.cooldown_expired(event):
            return AlertDecision(
                interrupt=False,
                timeout=event.timeout,
                event=event,
                state=AlertState.ACTIVE,
            )

        self.last_event_id = event.event_id
        self.last_event_message = event.message
        self.last_event_time = time.time()

        return AlertDecision(
            interrupt=True,
            timeout=event.timeout,
            event=event,
            state=AlertState.NEW,
        )

    def should_interrupt(self, event):
        return self.evaluate(event).interrupt

    def get_history(self):
        return list(self.history)
