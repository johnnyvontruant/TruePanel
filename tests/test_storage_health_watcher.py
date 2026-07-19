import json

from truepanel.mission_control.constants import Category, Priority
from truepanel.watchers.storage_health import (
    StorageEventRecorder,
    StorageHealthDiffer,
    StorageHealthWatcher,
)


def device(
    *,
    name="sdc",
    serial="SERIAL-3",
    label="Bay 3",
    state="healthy",
    message="healthy",
    temperature=40,
    reallocated=0,
    pending=0,
    uncorrectable=0,
    interface_errors=0,
):
    return {
        "device": name,
        "device_path": f"/dev/{name}",
        "serial": serial,
        "label": label,
        "state": state,
        "message": message,
        "temperature_c": temperature,
        "telemetry": {
            "temperature_c": temperature,
            "reallocated_sectors": reallocated,
            "pending_sectors": pending,
            "offline_uncorrectable": uncorrectable,
            "interface_errors": interface_errors,
        },
    }


def report(*devices):
    return {
        "device_count": len(devices),
        "devices": list(devices),
    }


def test_initial_healthy_snapshot_is_silent():
    watcher = StorageHealthWatcher(
        report_provider=lambda: report(device()),
        interval=0,
    )

    assert watcher(None) is None
    assert watcher.pending_count == 0


def test_initial_critical_condition_is_emitted():
    watcher = StorageHealthWatcher(
        report_provider=lambda: report(
            device(
                state="critical",
                message="pending sectors: 1608",
                reallocated=15376,
                pending=1608,
                uncorrectable=1608,
            )
        ),
        interval=0,
    )

    event = watcher(None)

    assert event is not None
    assert event.priority == Priority.CRITICAL
    assert event.category == Category.STORAGE
    assert event.title == "Drive Critical"
    assert event.message == "pending sectors: 1608"
    assert event.event_id == "storage.sdc.initial_condition"


def test_unchanged_critical_condition_is_not_repeated():
    current = report(
        device(
            state="critical",
            message="pending sectors: 1608",
            pending=1608,
            uncorrectable=1608,
        )
    )

    watcher = StorageHealthWatcher(
        report_provider=lambda: current,
        interval=0,
    )

    assert watcher(None) is not None
    assert watcher(None) is None
    assert watcher(None) is None


def test_health_degradation_emits_critical_event():
    reports = iter(
        [
            report(device()),
            report(
                device(
                    state="critical",
                    message="pending sectors: 12",
                    pending=12,
                    uncorrectable=12,
                )
            ),
        ]
    )

    watcher = StorageHealthWatcher(
        report_provider=lambda: next(reports),
        interval=0,
    )

    assert watcher(None) is None

    event = watcher(None)

    assert event.priority == Priority.CRITICAL
    assert event.event_id == "storage.sdc.health_degraded"
    assert event.message == "pending sectors: 12"


def test_media_counter_increase_is_emitted_without_state_change():
    reports = iter(
        [
            report(
                device(
                    state="critical",
                    pending=10,
                    uncorrectable=10,
                )
            ),
            report(
                device(
                    state="critical",
                    pending=12,
                    uncorrectable=11,
                )
            ),
        ]
    )

    watcher = StorageHealthWatcher(
        report_provider=lambda: next(reports),
        interval=0,
        emit_initial_conditions=False,
    )

    assert watcher(None) is None

    event = watcher(None)

    assert event.priority == Priority.CRITICAL
    assert event.title == "Media Errors"
    assert "pending 10->12" in event.message
    assert "uncorrectable 10->11" in event.message


def test_missing_device_is_critical():
    reports = iter(
        [
            report(device()),
            report(),
        ]
    )

    watcher = StorageHealthWatcher(
        report_provider=lambda: next(reports),
        interval=0,
    )

    assert watcher(None) is None

    event = watcher(None)

    assert event.priority == Priority.CRITICAL
    assert event.title == "Drive Missing"
    assert event.message == "Bay 3 disappeared"


def test_inserted_device_is_informational():
    reports = iter(
        [
            report(),
            report(device()),
        ]
    )

    watcher = StorageHealthWatcher(
        report_provider=lambda: next(reports),
        interval=0,
    )

    assert watcher(None) is None

    event = watcher(None)

    assert event.priority == Priority.INFO
    assert event.title == "Drive Detected"
    assert event.message == "Bay 3 detected"


def test_recovery_event_is_healthy():
    reports = iter(
        [
            report(
                device(
                    state="critical",
                    pending=10,
                )
            ),
            report(device()),
        ]
    )

    watcher = StorageHealthWatcher(
        report_provider=lambda: next(reports),
        interval=0,
        emit_initial_conditions=False,
    )

    assert watcher(None) is None

    event = watcher(None)

    assert event.priority == Priority.HEALTHY
    assert event.title == "Drive Recovered"
    assert event.message == "Bay 3 healthy"


def test_serial_identity_survives_device_name_change():
    differ = StorageHealthDiffer()

    old = differ.snapshot(
        report(
            device(
                name="sdc",
                serial="STABLE-SERIAL",
            )
        )
    )
    new = differ.snapshot(
        report(
            device(
                name="sdh",
                serial="STABLE-SERIAL",
            )
        )
    )

    changes = differ.compare(old, new)

    assert changes == []


def test_large_temperature_increase_is_emitted():
    reports = iter(
        [
            report(device(temperature=40)),
            report(device(temperature=46)),
        ]
    )

    watcher = StorageHealthWatcher(
        report_provider=lambda: next(reports),
        interval=0,
    )

    assert watcher(None) is None

    event = watcher(None)

    assert event.priority == Priority.WARNING
    assert event.title == "Drive Temperature"
    assert event.message == "temperature 40C->46C"


def test_poll_interval_prevents_repeated_collection():
    calls = []
    times = iter([0.0, 10.0, 60.0])

    def provider():
        calls.append(True)
        return report(device())

    watcher = StorageHealthWatcher(
        report_provider=provider,
        interval=60,
        clock=lambda: next(times),
    )

    assert watcher(None) is None
    assert watcher(None) is None
    assert watcher(None) is None
    assert len(calls) == 2


def test_multiple_changes_are_queued_by_priority():
    reports = iter(
        [
            report(
                device(
                    name="sda",
                    serial="A",
                    label="Bay 1",
                ),
                device(
                    name="sdb",
                    serial="B",
                    label="Bay 2",
                ),
            ),
            report(
                device(
                    name="sda",
                    serial="A",
                    label="Bay 1",
                    state="warning",
                    message="temperature 55C",
                    temperature=55,
                ),
            ),
        ]
    )

    watcher = StorageHealthWatcher(
        report_provider=lambda: next(reports),
        interval=0,
    )

    assert watcher(None) is None

    first = watcher(None)
    second = watcher(None)

    assert first.priority == Priority.CRITICAL
    assert first.title == "Drive Missing"
    assert second.priority == Priority.WARNING


def test_recorder_writes_replayable_jsonl(tmp_path):
    path = tmp_path / "storage-events.jsonl"
    recorder = StorageEventRecorder(path)

    watcher = StorageHealthWatcher(
        report_provider=lambda: report(
            device(
                state="critical",
                message="pending sectors: 1608",
                pending=1608,
            )
        ),
        recorder=recorder,
        interval=0,
    )

    event = watcher(None)

    assert event is not None
    assert path.exists()

    payload = json.loads(
        path.read_text(encoding="utf-8").strip()
    )

    assert payload["event"]["priority_name"] == "CRITICAL"
    assert payload["event"]["category"] == "storage"
    assert payload["change"]["new"]["physical_bay"] is None
    assert payload["change"]["new"]["pending_sectors"] == 1608
