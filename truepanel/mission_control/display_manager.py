"""
Display Manager

Coordinates Mission Control events, Alert Manager decisions, and LCD-safe
rendering. It does not talk directly to LCD hardware.
"""

from dataclasses import dataclass
from typing import Optional

from .constants import Priority
from .event import MissionEvent
from .renderer import render_event
from truepanel.display.widgets import progress_bar


class DisplayMode:
    NORMAL = "normal"
    ALERT = "alert"
    HISTORY = "history"
    QUEUE = "queue"


@dataclass
class DisplayFrame:
    mode: str

    line1: str
    line2: str

    priority: Priority

    timeout: int
    interrupt: bool

    event: Optional[MissionEvent] = None

    @property
    def lines(self):
        return [
            self.line1[:16],
            self.line2[:16],
        ]


class DisplayManager:
    def __init__(self, mission, alert_manager):
        self.mission = mission
        self.alert_manager = alert_manager
        self.mode = DisplayMode.NORMAL
        self.history_index = 0
        self.queue_index = 0

    def evaluate(self, state):
        event = self.mission.evaluate(state)
        decision = self.alert_manager.evaluate(event)

        if decision.interrupt:
            self.mode = DisplayMode.ALERT
            return DisplayFrame(
                mode=self.mode,
                line1="*** ALERT ***",
                line2=event.title,
                priority=event.priority,
                timeout=2,
                interrupt=True,
                event=event,
            )

        self.mode = DisplayMode.NORMAL
        rendered = render_event(event)

        return DisplayFrame(
            mode=self.mode,
            line1=rendered[0],
            line2=rendered[1],
            priority=event.priority,
            timeout=event.timeout,
            interrupt=False,
            event=event,
        )

    def render_alert_detail(self, event):
        if event.event_id in ("storage.scrub", "storage.resilver"):
            try:
                percent = int(str(event.message).strip("%"))
                return DisplayFrame(
                    mode=DisplayMode.ALERT,
                    line1=f"{event.title} {percent}%",
                    line2=progress_bar(percent),
                    priority=event.priority,
                    timeout=event.timeout,
                    interrupt=True,
                    event=event,
                )
            except Exception:
                pass

        rendered = render_event(event)

        return DisplayFrame(
            mode=DisplayMode.ALERT,
            line1=rendered[0],
            line2=rendered[1],
            priority=event.priority,
            timeout=event.timeout,
            interrupt=True,
            event=event,
        )

    def render_history(self):
        history = self.alert_manager.get_history()

        if not history:
            return DisplayFrame(
                mode=DisplayMode.HISTORY,
                line1="Alert History",
                line2="No Alerts",
                priority=Priority.INFO,
                timeout=5,
                interrupt=False,
                event=None,
            )

        if self.history_index >= len(history):
            self.history_index = 0

        event = history[self.history_index]

        return DisplayFrame(
            mode=DisplayMode.HISTORY,
            line1=f"Alert {self.history_index + 1}/{len(history)}",
            line2=event.title,
            priority=event.priority,
            timeout=5,
            interrupt=False,
            event=event,
        )

    def next_history(self):
        history = self.alert_manager.get_history()

        if not history:
            self.history_index = 0
            return self.render_history()

        self.history_index = (self.history_index + 1) % len(history)
        return self.render_history()

    def render_event_queue(self):
        history = self.alert_manager.get_history()

        if not history:
            return DisplayFrame(
                mode=DisplayMode.QUEUE,
                line1="No Alerts",
                line2="System Quiet",
                priority=Priority.HEALTHY,
                timeout=5,
                interrupt=False,
                event=None,
            )

        if self.queue_index >= len(history):
            self.queue_index = 0

        event = history[self.queue_index]

        return DisplayFrame(
            mode=DisplayMode.QUEUE,
            line1=f"Queue {self.queue_index + 1}/{len(history)}",
            line2=event.title,
            priority=event.priority,
            timeout=5,
            interrupt=False,
            event=event,
        )

    def next_event_queue(self):
        history = self.alert_manager.get_history()

        if not history:
            self.queue_index = 0
            return self.render_event_queue()

        self.queue_index = (self.queue_index + 1) % len(history)
        return self.render_event_queue()
