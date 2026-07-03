"""
Display Manager

Coordinates Mission Control events, Alert Manager decisions, and LCD-safe
rendering. It does not talk directly to LCD hardware.
"""

from dataclasses import dataclass
from typing import Optional

from .event import MissionEvent
from .renderer import render_event


class DisplayMode:
    NORMAL = "normal"
    ALERT = "alert"
    HISTORY = "history"


@dataclass
class DisplayFrame:
    mode: str
    lines: list[str]
    timeout: int
    interrupt: bool
    event: Optional[MissionEvent] = None


class DisplayManager:
    def __init__(self, mission, alert_manager):
        self.mission = mission
        self.alert_manager = alert_manager
        self.mode = DisplayMode.NORMAL
        self.history_index = 0

    def evaluate(self, state):
        event = self.mission.evaluate(state)
        decision = self.alert_manager.evaluate(event)

        if decision.interrupt:
            self.mode = DisplayMode.ALERT
            return DisplayFrame(
                mode=self.mode,
                event=event,
                lines=["*** ALERT ***", event.title[:16]],
                timeout=2,
                interrupt=True,
            )

        self.mode = DisplayMode.NORMAL
        return DisplayFrame(
            mode=self.mode,
            event=event,
            lines=render_event(event),
            timeout=event.timeout,
            interrupt=False,
        )

    def render_alert_detail(self, event):
        return DisplayFrame(
            mode=DisplayMode.ALERT,
            event=event,
            lines=render_event(event),
            timeout=event.timeout,
            interrupt=True,
        )

    def render_history(self):
        history = self.alert_manager.get_history()

        if not history:
            return DisplayFrame(
                mode=DisplayMode.HISTORY,
                event=None,
                lines=["Alert History", "No Alerts"],
                timeout=5,
                interrupt=False,
            )

        if self.history_index >= len(history):
            self.history_index = 0

        event = history[self.history_index]

        return DisplayFrame(
            mode=DisplayMode.HISTORY,
            event=event,
            lines=[
                f"Alert {self.history_index + 1}/{len(history)}"[:16],
                event.title[:16],
            ],
            timeout=5,
            interrupt=False,
        )

    def next_history(self):
        history = self.alert_manager.get_history()

        if not history:
            self.history_index = 0
            return self.render_history()

        self.history_index = (self.history_index + 1) % len(history)
        return self.render_history()
