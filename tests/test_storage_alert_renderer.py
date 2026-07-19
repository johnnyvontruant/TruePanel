from types import SimpleNamespace

from truepanel.mission_control.alert_manager import AlertManager
from truepanel.mission_control.constants import Category, Priority
from truepanel.mission_control.display_manager import (
    DisplayManager,
    DisplayMode,
)
from truepanel.mission_control.event import MissionEvent
from truepanel.mission_control.storage_alerts import (
    StorageAlertContent,
    render_storage_alert,
)


def event(
    change_type,
    *,
    title="Drive Critical",
    message="storage condition",
    priority=Priority.CRITICAL,
    **metadata,
):
    payload = {
        "change_type": change_type,
        "label": "Bay 3",
        "physical_bay": 3,
        "device": "sdc",
        "old_state": None,
        "new_state": "critical",
        "temperature_c": 38,
        "pending_sectors": 0,
        "offline_uncorrectable": 0,
        "reallocated_sectors": 0,
        "interface_errors": 0,
    }
    payload.update(metadata)

    return MissionEvent(
        priority=priority,
        title=title,
        message=message,
        category=Category.STORAGE,
        timeout=10,
        event_id=f"storage.sdc.{change_type}",
        source="storage_health_watcher",
        metadata=payload,
    )


def manager():
    mission = SimpleNamespace(evaluate=lambda state: None)
    registry = SimpleNamespace(dashboard_pages=[])

    return DisplayManager(
        mission,
        AlertManager(),
        config={},
        registry=registry,
    )


def test_non_structured_event_uses_no_storage_renderer():
    generic = MissionEvent(
        priority=Priority.WARNING,
        title="Generic",
        message="Fallback",
        category=Category.STORAGE,
    )

    assert render_storage_alert(generic) is None


def test_missing_drive_renderer():
    content = render_storage_alert(
        event(
            "device_missing",
            new_state=None,
            old_state="warning",
        )
    )

    assert content == StorageAlertContent(
        line1="DRIVE MISSING",
        line2="Bay 3",
    )


def test_inserted_drive_renderer():
    content = render_storage_alert(
        event(
            "device_inserted",
            priority=Priority.INFO,
            new_state="healthy",
        )
    )

    assert content.line1 == "NEW DRIVE"
    assert content.line2 == "Bay 3 Healthy"


def test_recovered_drive_renderer():
    content = render_storage_alert(
        event(
            "recovered",
            priority=Priority.HEALTHY,
            old_state="critical",
            new_state="healthy",
        )
    )

    assert content.line1 == "DRIVE RECOVERED"
    assert content.line2 == "Bay 3 Healthy"


def test_temperature_renderer():
    content = render_storage_alert(
        event(
            "temperature_increased",
            priority=Priority.WARNING,
            temperature_c=54,
        )
    )

    assert content.line1 == "DRIVE TEMP"
    assert content.line2 == "Bay 3 54 C"


def test_pending_sectors_take_display_priority():
    content = render_storage_alert(
        event(
            "initial_condition",
            pending_sectors=1608,
            offline_uncorrectable=1608,
            reallocated_sectors=15376,
        )
    )

    assert content.line1 == "PENDING SECTORS"
    assert content.line2 == "Bay 3 1608"


def test_offline_uncorrectable_is_used_without_pending_sectors():
    content = render_storage_alert(
        event(
            "media_counter_increased",
            pending_sectors=0,
            offline_uncorrectable=42,
            reallocated_sectors=900,
        )
    )

    assert content.line1 == "UNCORRECTABLE"
    assert content.line2 == "Bay 3 42"


def test_reallocated_sectors_are_used_when_more_severe_counters_clear():
    content = render_storage_alert(
        event(
            "media_counter_increased",
            pending_sectors=0,
            offline_uncorrectable=0,
            reallocated_sectors=15376,
        )
    )

    assert content.line1 == "REALLOCATED"
    assert content.line2 == "Bay 3 15376"


def test_critical_state_without_counters_gets_state_screen():
    content = render_storage_alert(
        event(
            "state_changed",
            pending_sectors=0,
            offline_uncorrectable=0,
            reallocated_sectors=0,
        )
    )

    assert content.line1 == "DRIVE CRITICAL"
    assert content.line2 == "Bay 3 Critical"


def test_display_manager_uses_storage_alert_content():
    storage_event = event(
        "initial_condition",
        pending_sectors=1608,
        reallocated_sectors=15376,
    )

    frame = manager().render_alert_detail(storage_event)

    assert frame.mode == DisplayMode.ALERT
    assert frame.interrupt is True
    assert frame.priority == Priority.CRITICAL
    assert frame.event is storage_event
    assert frame.line1 == "PENDING SECTORS"
    assert frame.line2 == "Bay 3 1608"
    assert frame.lines == [
        "PENDING SECTORS ",
        "Bay 3 1608      ",
    ]


def test_display_manager_preserves_generic_alert_fallback():
    generic = MissionEvent(
        priority=Priority.CRITICAL,
        title="Power Failure",
        message="UPS offline",
        event_id="power.ups.failure",
    )

    frame = manager().render_alert_detail(generic)

    assert frame.mode == DisplayMode.ALERT
    assert frame.interrupt is True
    assert frame.event is generic
    assert "Power Failure" in frame.line2
