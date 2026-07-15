from dataclasses import dataclass

from truepanel.mission_control.constants import Priority
from truepanel.mission_control.display_manager import (
    DisplayManager,
)


@dataclass
class FakeEvent:
    priority: Priority
    title: str = "Nominal"
    timeout: int = 5
    event_id: str = "system.status"
    message: str = "Nominal"


class FakeMission:
    def __init__(self, event):
        self.event = event

    def evaluate(self, state):
        return self.event


class FakeAlertManager:
    def __init__(self, history=()):
        self.history = list(history)

    def get_history(self):
        return list(self.history)


class EmptyRegistry:
    dashboard_pages = []


def make_manager(event, history=()):
    return DisplayManager(
        FakeMission(event),
        FakeAlertManager(history),
        registry=EmptyRegistry(),
    )


def test_healthy_mission_status_instrument():
    event = FakeEvent(
        priority=Priority.HEALTHY,
    )
    manager = make_manager(event)

    frame = manager._dashboard_home({})

    assert frame.lines == [
        " MISSION READY  ",
        "SYS ###### 100% ",
    ]
    assert frame.priority is Priority.HEALTHY
    assert frame.event is event


def test_active_alert_mission_status_instrument():
    event = FakeEvent(
        priority=Priority.CRITICAL,
        title="High Temp",
    )
    manager = make_manager(event)

    frame = manager._dashboard_home({})

    assert frame.lines == [
        " MISSION ALERT  ",
        "ALT ###### 100% ",
    ]
    assert frame.priority is Priority.CRITICAL


def test_stored_alert_watch_instrument():
    event = FakeEvent(
        priority=Priority.HEALTHY,
    )
    stored = FakeEvent(
        priority=Priority.WARNING,
        title="Stored Alert",
    )
    manager = make_manager(
        event,
        history=[stored, stored],
    )

    frame = manager._dashboard_home({})

    assert frame.lines == [
        "  SYSTEM WATCH  ",
        "ALT ##----  40% ",
    ]
    assert frame.priority is Priority.WARNING
    assert frame.event is stored
