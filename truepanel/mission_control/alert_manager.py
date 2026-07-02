"""
Alert Manager

Determines whether a MissionEvent should interrupt normal display flow.
"""

import time

from .constants import Priority


class AlertManager:
    def __init__(self, interrupt_priority=Priority.WARNING):
        self.interrupt_priority = interrupt_priority
        self.last_event_id = None
        self.last_event_time = 0

    def should_interrupt(self, event):
        if event.priority < self.interrupt_priority:
            return False

        now = time.time()

        # Avoid hammering the same alert repeatedly every refresh.
        if event.event_id == self.last_event_id:
            if now - self.last_event_time < event.timeout:
                return False

        self.last_event_id = event.event_id
        self.last_event_time = now
        return True
