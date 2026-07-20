"""
Alert Manager

Tracks MissionEvent alert state, suppresses duplicate alerts, stores alert
history, decides whether an event should interrupt normal display flow, and
controls one-shot audible alert notifications.
"""

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
    def __init__(
        self,
        interrupt_priority=Priority.WARNING,
        history_size=25,
    ):
        self.interrupt_priority = interrupt_priority

        # Per-incident display interruption latches.
        self.display_incidents = {}
        self.healthy_observations = 0
        self.recovery_observations = 3

        # Compatibility fields for diagnostics.
        self.last_event_id = None
        self.last_event_message = None
        self.last_event_priority = None

        # Audible notification state.
        self.last_beep_event_id = None
        self.last_beep_message = None
        self.last_beep_priority = None

        self.history = deque(maxlen=history_size)

    def is_alert(self, event):
        return event.priority >= self.interrupt_priority

    def reset_display_state(self):
        self.display_incidents.clear()
        self.healthy_observations = 0
        self.last_event_id = None
        self.last_event_message = None
        self.last_event_priority = None

    def cooldown_expired(self, event):
        previous = self.display_incidents.get(
            event.event_id
        )

        if previous is None:
            return True

        previous_message, previous_priority = previous

        message_changed = (
            event.message != previous_message
        )

        priority_increased = (
            event.message == previous_message
            and event.priority > previous_priority
        )

        return message_changed or priority_increased

    def record(self, event):
        if not self.is_alert(event):
            return False

        if self.history:
            last = self.history[0]

            if (
                last.event_id == event.event_id
                and last.message == event.message
            ):
                return False

        self.history.appendleft(event)
        return True

    def reset_audible_state(self):
        """
        Re-arm audible notifications after the system returns healthy.
        """

        self.last_beep_event_id = None
        self.last_beep_message = None
        self.last_beep_priority = None

    def should_beep(self, event):
        """
        Return True only when an audible alert is warranted.

        A beep is produced when:

        * a new alert first appears;
        * a different alert appears;
        * the alert message changes; or
        * an existing alert escalates in priority.

        A persistent, unchanged alert remains silent.
        """

        if event is None or not self.is_alert(event):
            self.reset_audible_state()
            return False

        event_id = event.event_id
        message = event.message
        priority = event.priority

        different_alert = (
            event_id != self.last_beep_event_id
            or message != self.last_beep_message
        )

        priority_increased = (
            self.last_beep_priority is not None
            and priority > self.last_beep_priority
        )

        should_sound = (
            self.last_beep_event_id is None
            or different_alert
            or priority_increased
        )

        if should_sound:
            self.last_beep_event_id = event_id
            self.last_beep_message = message
            self.last_beep_priority = priority

        return should_sound

    def evaluate(self, event):
        if not self.is_alert(event):
            self.healthy_observations += 1
            self.reset_audible_state()

            if (
                self.healthy_observations
                >= self.recovery_observations
            ):
                self.reset_display_state()

            return AlertDecision(
                interrupt=False,
                timeout=event.timeout,
                event=event,
                state=AlertState.RESOLVED,
            )

        self.healthy_observations = 0
        self.record(event)

        should_interrupt = self.cooldown_expired(
            event
        )

        previous = self.display_incidents.get(
            event.event_id
        )

        stored_priority = event.priority

        if (
            previous is not None
            and previous[0] == event.message
            and previous[1] > stored_priority
        ):
            stored_priority = previous[1]

        self.display_incidents[event.event_id] = (
            event.message,
            stored_priority,
        )

        self.last_event_id = event.event_id
        self.last_event_message = event.message
        self.last_event_priority = stored_priority

        if not should_interrupt:
            return AlertDecision(
                interrupt=False,
                timeout=event.timeout,
                event=event,
                state=AlertState.ACTIVE,
            )

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
