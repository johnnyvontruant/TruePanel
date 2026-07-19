from truepanel.mission_control.constants import Category, Priority
from truepanel.mission_control.event import MissionEvent
from truepanel.watchers.storage_health import StorageHealthChange


def snapshot(
    *,
    state="critical",
    pending=1608,
    reallocated=15376,
    offline_uncorrectable=1608,
):
    return {
        "key": "serial:FAILED-DRIVE",
        "device": "sdc",
        "device_path": "/dev/sdc",
        "label": "Bay 3",
        "serial": "FAILED-DRIVE",
        "model": "ST8000NE001-2M7101",
        "category": "ata",
        "physical_bay": 3,
        "state": state,
        "message": "pending sectors: 1608",
        "temperature_c": 38,
        "smart_passed": True,
        "reallocated_sectors": reallocated,
        "pending_sectors": pending,
        "offline_uncorrectable": offline_uncorrectable,
        "interface_errors": 0,
        "percentage_used": None,
        "available_spare": None,
        "source": "smartctl",
        "collected_at": "2026-07-17T00:00:00+00:00",
    }


def test_mission_event_metadata_defaults_to_empty_dictionary():
    event = MissionEvent(
        priority=Priority.INFO,
        title="Test",
        message="Message",
    )

    assert event.metadata == {}


def test_mission_event_metadata_is_not_shared_between_events():
    first = MissionEvent(
        priority=Priority.INFO,
        title="First",
        message="One",
    )
    second = MissionEvent(
        priority=Priority.INFO,
        title="Second",
        message="Two",
    )

    first.metadata["value"] = 42

    assert second.metadata == {}


def test_existing_positional_event_construction_remains_compatible():
    event = MissionEvent(
        Priority.WARNING,
        "Legacy Event",
        "Still works",
        Category.SYSTEM,
        9,
        "legacy.event",
        "legacy_source",
    )

    assert event.priority == Priority.WARNING
    assert event.title == "Legacy Event"
    assert event.message == "Still works"
    assert event.metadata == {}


def test_storage_event_contains_structured_drive_metadata():
    new = snapshot()

    change = StorageHealthChange(
        change_type="initial_condition",
        device_key="serial:FAILED-DRIVE",
        label="Bay 3",
        old_state=None,
        new_state="critical",
        message="pending sectors: 1608",
        priority=Priority.CRITICAL,
        old=None,
        new=new,
    )

    event = change.to_event()

    assert event.title == "Drive Critical"
    assert event.category == Category.STORAGE
    assert event.metadata["change_type"] == "initial_condition"
    assert event.metadata["device"] == "sdc"
    assert event.metadata["device_path"] == "/dev/sdc"
    assert event.metadata["label"] == "Bay 3"
    assert event.metadata["physical_bay"] == 3
    assert event.metadata["serial"] == "FAILED-DRIVE"
    assert event.metadata["new_state"] == "critical"
    assert event.metadata["temperature_c"] == 38
    assert event.metadata["smart_passed"] is True
    assert event.metadata["pending_sectors"] == 1608
    assert event.metadata["reallocated_sectors"] == 15376
    assert event.metadata["offline_uncorrectable"] == 1608


def test_missing_drive_metadata_uses_previous_snapshot():
    old = snapshot(state="warning")

    change = StorageHealthChange(
        change_type="device_missing",
        device_key="serial:FAILED-DRIVE",
        label="Bay 3",
        old_state="warning",
        new_state=None,
        message="Bay 3 disappeared",
        priority=Priority.CRITICAL,
        old=old,
        new=None,
    )

    event = change.to_event()

    assert event.title == "Drive Missing"
    assert event.metadata["device"] == "sdc"
    assert event.metadata["label"] == "Bay 3"
    assert event.metadata["physical_bay"] == 3
    assert event.metadata["old_state"] == "warning"
    assert event.metadata["new_state"] is None


def test_inserted_drive_metadata_uses_current_snapshot():
    new = snapshot(
        state="healthy",
        pending=0,
        reallocated=0,
        offline_uncorrectable=0,
    )

    change = StorageHealthChange(
        change_type="device_inserted",
        device_key="serial:REPLACEMENT",
        label="Bay 3",
        old_state=None,
        new_state="healthy",
        message="Bay 3 detected",
        priority=Priority.INFO,
        old=None,
        new=new,
    )

    event = change.to_event()

    assert event.title == "Drive Detected"
    assert event.metadata["new_state"] == "healthy"
    assert event.metadata["pending_sectors"] == 0
