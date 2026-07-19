from types import SimpleNamespace

from truepanel.mission_control.constants import (
    Category,
    Priority,
)
from truepanel.mission_control.display_manager import (
    DisplayManager,
)
from truepanel.mission_control.event import MissionEvent


class Mission:
    def __init__(self, event):
        self.event = event

    def evaluate(self, state):
        return self.event


class AlertManager:
    def evaluate(self, event):
        return SimpleNamespace(interrupt=True)

    def get_history(self):
        return []


class EmptyRegistry:
    dashboard_pages = []


def bay_event(
    change_type="health_degraded",
    new_state="critical",
):
    return MissionEvent(
        priority=Priority.CRITICAL,
        title="Drive Critical",
        message="pending sectors",
        category=Category.STORAGE,
        event_id="storage.sda.health_degraded",
        source="storage_health_watcher",
        metadata={
            "physical_bay": 1,
            "label": "Bay 1",
            "change_type": change_type,
            "new_state": new_state,
            "pending_sectors": 2,
        },
    )


def manager_for(event):
    return DisplayManager(
        mission=Mission(event),
        alert_manager=AlertManager(),
        registry=EmptyRegistry(),
    )


def test_bay_storage_event_does_not_interrupt_lcd():
    manager = manager_for(bay_event())

    frame = manager.evaluate({})

    assert frame.interrupt is False
    assert manager.latest_storage_event is not None


def test_storage_dashboard_shows_drive_detail():
    manager = manager_for(bay_event())
    manager.evaluate({})

    frame = manager._dashboard_storage({})

    assert frame.interrupt is False
    assert frame.lines[0].strip() == "PENDING SECTORS"
    assert frame.lines[1].strip() == "Bay 1 2"


def test_recovery_clears_drive_detail():
    manager = manager_for(
        bay_event(
            change_type="recovered",
            new_state="healthy",
        )
    )

    manager.latest_storage_event = bay_event()
    manager.evaluate({})

    assert manager.latest_storage_event is None


def test_non_bay_critical_event_still_interrupts():
    event = MissionEvent(
        priority=Priority.CRITICAL,
        title="System Critical",
        message="system problem",
        category=Category.SYSTEM,
    )

    manager = manager_for(event)
    frame = manager.evaluate({})

    assert frame.interrupt is True
