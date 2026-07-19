from types import SimpleNamespace

from truepanel.mission_control.alert_manager import AlertManager
from truepanel.mission_control.constants import Category, Priority
from truepanel.mission_control.display_manager import (
    DisplayManager,
    DisplayMode,
)
from truepanel.mission_control.storage_alerts import render_storage_alert
from truepanel.mission_control.watchers.zfs import ZFSOperationWatcher


def state(
    *,
    scrub=False,
    resilver=False,
    percent=None,
    remaining=None,
    problem=False,
):
    return {
        "zfs_activity": {
            "scrub_running": scrub,
            "resilver_running": resilver,
            "percent": percent,
            "remaining": remaining,
            "problem": problem,
        }
    }


def manager():
    mission = SimpleNamespace(evaluate=lambda current: None)
    registry = SimpleNamespace(dashboard_pages=[])

    return DisplayManager(
        mission,
        AlertManager(),
        config={},
        registry=registry,
    )


def test_no_operation_returns_none():
    watcher = ZFSOperationWatcher()

    assert watcher(state()) is None


def test_scrub_start_emits_structured_event():
    watcher = ZFSOperationWatcher()

    event = watcher(
        state(
            scrub=True,
            percent=4,
            remaining="2h 10m",
        )
    )

    assert event.event_id == "storage.scrub"
    assert event.title == "SCRUB"
    assert event.message == "4%"
    assert event.priority == Priority.INFO
    assert event.category == Category.STORAGE
    assert event.metadata["change_type"] == "operation_started"
    assert event.metadata["operation"] == "scrub"
    assert event.metadata["phase"] == "started"
    assert event.metadata["percent"] == 4
    assert event.metadata["remaining"] == "2h 10m"


def test_scrub_progress_tracks_previous_percentage():
    watcher = ZFSOperationWatcher()

    watcher(state(scrub=True, percent=4))
    event = watcher(state(scrub=True, percent=27))

    assert event.event_id == "storage.scrub"
    assert event.message == "27%"
    assert event.metadata["change_type"] == "operation_progress"
    assert event.metadata["previous_percent"] == 4
    assert event.metadata["percent"] == 27


def test_scrub_completion_is_emitted_once():
    watcher = ZFSOperationWatcher()

    watcher(state(scrub=True, percent=92))
    completed = watcher(state())
    quiet = watcher(state())

    assert completed.event_id == "storage.scrub.completed"
    assert completed.title == "SCRUB DONE"
    assert completed.priority == Priority.HEALTHY
    assert completed.metadata["change_type"] == "operation_completed"
    assert completed.metadata["percent"] == 100
    assert completed.metadata["previous_percent"] == 92
    assert quiet is None


def test_resilver_takes_precedence_over_scrub():
    watcher = ZFSOperationWatcher()

    event = watcher(
        state(
            scrub=True,
            resilver=True,
            percent=12,
        )
    )

    assert event.event_id == "storage.resilver"
    assert event.metadata["operation"] == "resilver"


def test_resilver_lifecycle():
    watcher = ZFSOperationWatcher()

    started = watcher(state(resilver=True, percent=1))
    progress = watcher(state(resilver=True, percent=55))
    completed = watcher(state())

    assert started.metadata["phase"] == "started"
    assert progress.metadata["phase"] == "progress"
    assert completed.event_id == "storage.resilver.completed"
    assert completed.metadata["operation"] == "resilver"


def test_problem_event_escalates_to_warning():
    watcher = ZFSOperationWatcher()

    event = watcher(
        state(
            resilver=True,
            percent=31,
            remaining="I/O errors",
            problem=True,
        )
    )

    assert event.event_id == "storage.resilver.problem"
    assert event.priority == Priority.WARNING
    assert event.title == "RESILVER ALERT"
    assert event.message == "I/O errors"
    assert event.metadata["problem"] is True


def test_percentage_is_clamped_to_lcd_safe_range():
    watcher = ZFSOperationWatcher()

    event = watcher(
        state(
            scrub=True,
            percent=143,
        )
    )

    assert event.metadata["percent"] == 100
    assert event.message == "100%"


def test_active_operation_uses_graphical_progress_renderer():
    watcher = ZFSOperationWatcher()
    event = watcher(state(resilver=True, percent=42))

    frame = manager().render_alert_detail(event)

    assert frame.mode == DisplayMode.ALERT
    assert frame.interrupt is True
    assert frame.event is event
    assert "RESILVER" in frame.line1
    assert len(frame.lines[0]) == 16
    assert len(frame.lines[1]) == 16


def test_completed_operation_uses_storage_completion_screen():
    watcher = ZFSOperationWatcher()

    watcher(state(scrub=True, percent=99))
    event = watcher(state())

    content = render_storage_alert(event)

    assert content.line1 == "SCRUB DONE"
    assert content.line2 == "POOL ONLINE"

    frame = manager().render_alert_detail(event)

    assert frame.mode == DisplayMode.ALERT
    assert frame.line1 == "SCRUB DONE"
    assert frame.line2 == "POOL ONLINE"


def test_problem_uses_storage_alert_screen():
    watcher = ZFSOperationWatcher()

    event = watcher(
        state(
            scrub=True,
            percent=18,
            remaining="Read errors",
            problem=True,
        )
    )

    content = render_storage_alert(event)

    assert content.line1 == "SCRUB ALERT"
    assert content.line2 == "Read errors"
