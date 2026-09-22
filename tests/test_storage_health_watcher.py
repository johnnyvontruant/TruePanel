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


def test_temperature_warning_hysteresis_suppresses_44_45_chatter():
    differ = StorageHealthDiffer()

    previous = {
        "device:nvme0n1": {
            "key": "device:nvme0n1",
            "device": "nvme0n1",
            "label": "NVMe",
            "state": "warning",
            "message": "temperature 45°C",
            "temperature_c": 45,
        }
    }

    for temperature in (44, 45, 44, 43):
        raw_state = "warning" if temperature >= 45 else "healthy"
        current = {
            "device:nvme0n1": {
                **previous["device:nvme0n1"],
                "state": raw_state,
                "message": (
                    f"temperature {temperature}°C"
                    if raw_state == "warning"
                    else "healthy"
                ),
                "temperature_c": temperature,
            }
        }

        changes = differ.compare(previous, current)
        assert not [
            change
            for change in changes
            if change.change_type in {
                "recovered",
                "health_degraded",
                "health_improved",
            }
        ]

        effective = differ._apply_temperature_hysteresis(
            previous["device:nvme0n1"],
            current["device:nvme0n1"],
        )
        previous = {"device:nvme0n1": effective}


def test_temperature_warning_recovers_at_42_c():
    differ = StorageHealthDiffer()

    old = {
        "key": "device:nvme0n1",
        "device": "nvme0n1",
        "label": "NVMe",
        "state": "warning",
        "message": "temperature 45°C",
        "temperature_c": 43,
    }
    new = {
        **old,
        "state": "healthy",
        "message": "healthy",
        "temperature_c": 42,
    }

    changes = differ.compare(
        {"device:nvme0n1": old},
        {"device:nvme0n1": new},
    )

    assert len(changes) == 1
    assert changes[0].change_type == "recovered"
    assert changes[0].new_state == "healthy"


def test_temperature_critical_hysteresis_recovers_at_52_c():
    differ = StorageHealthDiffer()

    old = {
        "key": "device:nvme0n1",
        "device": "nvme0n1",
        "label": "NVMe",
        "state": "critical",
        "message": "temperature 55°C",
        "temperature_c": 54,
    }

    held = {
        **old,
        "state": "warning",
        "message": "temperature 53°C",
        "temperature_c": 53,
    }

    assert not differ.compare(
        {"device:nvme0n1": old},
        {"device:nvme0n1": held},
    )

    recovered = {
        **held,
        "temperature_c": 52,
    }

    changes = differ.compare(
        {"device:nvme0n1": old},
        {"device:nvme0n1": recovered},
    )

    assert len(changes) == 1
    assert changes[0].change_type == "health_improved"
    assert changes[0].new_state == "warning"


def test_non_temperature_recovery_is_not_held_by_hysteresis():
    differ = StorageHealthDiffer()

    old = {
        "key": "device:sda",
        "device": "sda",
        "label": "Disk",
        "state": "warning",
        "message": "reallocated sectors: 4",
        "temperature_c": 44,
    }
    new = {
        **old,
        "state": "healthy",
        "message": "healthy",
    }

    changes = differ.compare(
        {"device:sda": old},
        {"device:sda": new},
    )

    assert len(changes) == 1
    assert changes[0].change_type == "recovered"


def test_watcher_persists_temperature_hysteresis_between_polls():
    reports = iter(
        [
            report(
                device(
                    name="nvme0n1",
                    label="NVMe",
                    state="healthy",
                    message="healthy",
                    temperature=40,
                )
            ),
            report(
                device(
                    name="nvme0n1",
                    label="NVMe",
                    state="warning",
                    message="temperature 45°C",
                    temperature=45,
                )
            ),
            report(
                device(
                    name="nvme0n1",
                    label="NVMe",
                    state="healthy",
                    message="healthy",
                    temperature=44,
                )
            ),
            report(
                device(
                    name="nvme0n1",
                    label="NVMe",
                    state="warning",
                    message="temperature 45°C",
                    temperature=45,
                )
            ),
            report(
                device(
                    name="nvme0n1",
                    label="NVMe",
                    state="healthy",
                    message="healthy",
                    temperature=44,
                )
            ),
            report(
                device(
                    name="nvme0n1",
                    label="NVMe",
                    state="healthy",
                    message="healthy",
                    temperature=43,
                )
            ),
            report(
                device(
                    name="nvme0n1",
                    label="NVMe",
                    state="healthy",
                    message="healthy",
                    temperature=42,
                )
            ),
        ]
    )

    watcher = StorageHealthWatcher(
        report_provider=lambda: next(reports),
        interval=0,
    )

    assert watcher(None) is None

    warning = watcher(None)
    assert warning is not None
    assert warning.event_id == "storage.nvme0n1.health_degraded"

    # 44 → 45 → 44 → 43 must remain effectively WARNING.
    assert watcher(None) is None
    assert watcher(None) is None
    assert watcher(None) is None
    assert watcher(None) is None

    recovered = watcher(None)
    assert recovered is not None
    assert recovered.event_id == "storage.nvme0n1.recovered"

    assert watcher.pending_count == 0


def test_watcher_reconciles_temperature_led_on_poll_without_recovery_event():
    from truepanel.hardware.bay_leds import TVS671BayLedController
    from truepanel.mission_control.storage_bay_indicator import (
        StorageBayIndicator,
    )

    commands = []
    controller = TVS671BayLedController(
        command_writer=commands.append
    )
    indicator = StorageBayIndicator(controller)

    def snapshot(temperature):
        state = "warning" if temperature >= 45 else "healthy"
        return report({
            **device(
                name="sdc",
                serial="SERIAL-4",
                label="Bay 4",
                state=state,
                message=(
                    f"temperature {temperature}°C"
                    if state == "warning"
                    else "healthy"
                ),
                temperature=temperature,
            ),
            "physical_bay": 4,
        })

    reports = iter(
        snapshot(temp)
        for temp in (40, 45, 46, 48, 49, 45, 42)
    )
    watcher = StorageHealthWatcher(
        report_provider=lambda: next(reports),
        event_observers=[indicator],
        interval=0,
    )

    watcher.poll()
    assert commands == [0x09]

    entered = watcher.poll()
    assert len(entered) == 1
    assert entered[0].event_id.endswith("health_degraded")
    assert commands == [0x09]

    watcher.poll()
    watcher.poll()
    assert commands == [0x09]

    watcher.poll()
    assert commands == [0x09, 0x08]

    # At 45 C the health state is still WARNING and no recovery event fires.
    # The separate thermal LED policy must clear the stale identify channel.
    assert watcher.poll() == []
    assert commands == [0x09, 0x08, 0x09]
    assert controller.active_bays == ()

    watcher.poll()
    assert controller.active_bays == ()
