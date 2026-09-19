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
