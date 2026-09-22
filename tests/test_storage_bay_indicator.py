from truepanel.hardware.bay_leds import (
    TVS671BayLedController,
)
from truepanel.mission_control.constants import (
    Category,
    Priority,
)
from truepanel.mission_control.event import MissionEvent
from truepanel.mission_control.storage_bay_indicator import (
    StorageBayIndicator,
)


def event(
    *,
    priority=Priority.CRITICAL,
    change_type="health_degraded",
    new_state="critical",
    bay=1,
):
    return MissionEvent(
        priority=priority,
        title="Drive Critical",
        message="Pending sectors",
        category=Category.STORAGE,
        event_id="storage.sda.health_degraded",
        source="storage_health_watcher",
        metadata={
            "physical_bay": bay,
            "change_type": change_type,
            "new_state": new_state,
        },
    )


def test_warning_uses_flashing_identify_channel():
    commands = []
    controller = TVS671BayLedController(
        command_writer=commands.append
    )
    indicator = StorageBayIndicator(controller)

    assert indicator(
        event(
            bay=4,
            priority=Priority.WARNING,
            new_state="warning",
        )
    )
    assert commands == [0x08, 0x89]
    assert controller.active_bays == (4,)


def test_critical_uses_steady_error_channel():
    commands = []
    controller = TVS671BayLedController(
        command_writer=commands.append
    )
    indicator = StorageBayIndicator(controller)

    assert indicator(event(bay=4))
    assert commands == [0x09, 0x88]
    assert controller.active_bays == ()


def test_critical_state_wins_even_when_event_priority_is_warning():
    commands = []
    controller = TVS671BayLedController(
        command_writer=commands.append
    )
    indicator = StorageBayIndicator(controller)

    assert indicator(
        event(
            bay=3,
            priority=Priority.WARNING,
            change_type="media_counter_increased",
            new_state="critical",
        )
    )
    assert commands == [0x07, 0x86]


def test_warning_to_critical_switches_red_channels():
    commands = []
    controller = TVS671BayLedController(
        command_writer=commands.append
    )
    indicator = StorageBayIndicator(controller)

    indicator(
        event(
            bay=3,
            priority=Priority.WARNING,
            new_state="warning",
        )
    )
    indicator(event(bay=3))

    assert commands == [0x06, 0x87, 0x07, 0x86]
    assert controller.active_bays == ()


def test_recovery_clears_both_red_channels():
    commands = []
    controller = TVS671BayLedController(
        command_writer=commands.append
    )
    indicator = StorageBayIndicator(controller)

    indicator(event(bay=3))
    indicator(
        event(
            bay=3,
            priority=Priority.INFO,
            change_type="recovered",
            new_state="healthy",
        )
    )

    assert commands == [0x07, 0x86, 0x87]
    assert controller.active_bays == ()


def test_transient_warning_priority_does_not_latch_healthy_bay():
    commands = []
    controller = TVS671BayLedController(
        command_writer=commands.append
    )
    indicator = StorageBayIndicator(controller)

    assert indicator(
        event(
            bay=6,
            priority=Priority.WARNING,
            change_type="temperature_increased",
            new_state="healthy",
        )
    )

    assert commands == [0x0D, 0x8D]
    assert controller.active_bays == ()


def test_missing_drive_still_uses_steady_error_channel():
    commands = []
    controller = TVS671BayLedController(
        command_writer=commands.append
    )
    indicator = StorageBayIndicator(controller)

    assert indicator(
        event(
            bay=3,
            priority=Priority.CRITICAL,
            change_type="device_missing",
            new_state=None,
        )
    )

    assert commands == [0x07, 0x86]
    assert controller.active_bays == ()


def test_clear_on_start_clears_identify_and_error_channels():
    commands = []
    controller = TVS671BayLedController(
        command_writer=commands.append
    )

    StorageBayIndicator(
        controller,
        clear_on_start=True,
    )

    assert commands == [
        0x03,
        0x05,
        0x07,
        0x09,
        0x0B,
        0x0D,
        0x83,
        0x85,
        0x87,
        0x89,
        0x8B,
        0x8D,
    ]


def test_unstructured_event_does_not_touch_hardware():
    commands = []
    controller = TVS671BayLedController(
        command_writer=commands.append
    )
    indicator = StorageBayIndicator(controller)

    legacy = MissionEvent(
        priority=Priority.CRITICAL,
        title="SMART Fail",
        message="sda",
        category=Category.STORAGE,
        source="smart_watcher",
    )

    assert not indicator(legacy)
    assert commands == []


def _snapshot(bay, *, state, temperature, message):
    return {
        f"serial:BAY-{bay}": {
            "physical_bay": bay,
            "state": state,
            "temperature_c": temperature,
            "message": message,
        }
    }


def test_temperature_advisory_at_45_does_not_flash_physical_bay():
    commands = []
    controller = TVS671BayLedController(
        command_writer=commands.append
    )
    indicator = StorageBayIndicator(controller)

    # A genuine WARNING health transition can be dashboard-worthy without
    # triggering a red physical lamp before the higher thermal LED threshold.
    warning = event(
        bay=4, priority=Priority.WARNING, new_state="warning"
    )
    warning.metadata["health_message"] = "temperature 45°C"
    assert not indicator(warning)
    assert commands == []

    indicator.reconcile_snapshot(
        _snapshot(
            4, state="warning", temperature=45,
            message="temperature 45°C",
        )
    )
    assert commands == [0x09]
    assert controller.active_bays == ()


def test_temperature_lamp_requires_two_hot_polls_and_clears_at_45():
    commands = []
    controller = TVS671BayLedController(
        command_writer=commands.append
    )
    indicator = StorageBayIndicator(controller)

    indicator.reconcile_snapshot(
        _snapshot(
            2, state="warning", temperature=48,
            message="temperature 48°C",
        )
    )
    assert commands == []

    indicator.reconcile_snapshot(
        _snapshot(
            2, state="warning", temperature=49,
            message="temperature 49°C",
        )
    )
    assert commands == [0x04]
    assert controller.active_bays == (2,)

    # Hold the active warning in the hysteresis band.
    indicator.reconcile_snapshot(
        _snapshot(
            2, state="warning", temperature=46,
            message="temperature 46°C",
        )
    )
    assert commands == [0x04]

    indicator.reconcile_snapshot(
        _snapshot(
            2, state="warning", temperature=45,
            message="temperature 45°C",
        )
    )
    assert commands == [0x04, 0x05]
    assert controller.active_bays == ()


def test_temperature_at_50_activates_without_waiting_for_second_poll():
    commands = []
    indicator = StorageBayIndicator(
        TVS671BayLedController(command_writer=commands.append)
    )
    indicator.reconcile_snapshot(
        _snapshot(
            5, state="warning", temperature=50,
            message="temperature 50°C",
        )
    )
    assert commands == [0x0A]


def test_healthy_poll_clears_stale_identify_but_never_clears_critical():
    commands = []
    controller = TVS671BayLedController(
        command_writer=commands.append
    )
    indicator = StorageBayIndicator(controller)

    indicator.reconcile_snapshot(
        _snapshot(
            3, state="critical", temperature=40,
            message="pending sectors: 1608",
        )
    )
    assert commands == [0x86]

    indicator.reconcile_snapshot(
        _snapshot(
            1, state="healthy", temperature=40,
            message="healthy",
        )
    )
    assert commands == [0x86, 0x03]
    assert 0x87 not in commands


def test_non_temperature_warning_remains_flash_worthy():
    commands = []
    indicator = StorageBayIndicator(
        TVS671BayLedController(command_writer=commands.append)
    )
    indicator.reconcile_snapshot(
        _snapshot(
            4, state="warning", temperature=40,
            message="reallocated sectors: 3",
        )
    )
    assert commands == [0x08]


def test_missing_or_ambiguous_bay_evidence_cannot_clear_led():
    commands = []
    indicator = StorageBayIndicator(
        TVS671BayLedController(command_writer=commands.append)
    )
    indicator.reconcile_snapshot(
        {
            "missing": {"physical_bay": 3, "state": "unknown"},
            "a": {
                "physical_bay": 2, "state": "healthy",
                "temperature_c": 40,
            },
            "b": {
                "physical_bay": 2, "state": "healthy",
                "temperature_c": 40,
            },
        }
    )
    assert commands == []
