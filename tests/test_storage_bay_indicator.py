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


def test_fault_turns_matching_bay_on():
    commands = []
    controller = TVS671BayLedController(
        command_writer=commands.append
    )
    indicator = StorageBayIndicator(controller)

    assert indicator(event(bay=4))
    assert commands == [0x08]
    assert controller.active_bays == (4,)


def test_recovery_turns_matching_bay_off():
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

    assert commands == [0x06, 0x07]
    assert controller.active_bays == ()


def test_multiple_bay_faults_remain_active():
    commands = []
    controller = TVS671BayLedController(
        command_writer=commands.append
    )
    indicator = StorageBayIndicator(controller)

    indicator(event(bay=1))
    indicator(event(bay=6))

    assert commands == [0x02, 0x0C]
    assert controller.active_bays == (1, 6)


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
