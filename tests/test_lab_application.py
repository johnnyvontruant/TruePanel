import pytest

from truepanel.lab.application import (
    CatalogCommandSummary,
    LaboratoryApplication,
    LaboratoryApplicationConfiguration,
    build_a125_laboratory_application,
)
from truepanel.lab.execution import (
    ExecutionStatus,
)
from truepanel.lab.execution_events import (
    ExecutionEventRecorder,
)
from truepanel.lab.execution_service import (
    build_a125_execution_service,
)
from truepanel.lab.interlock import (
    ExecutionMode,
)


class FakeController:
    def __init__(self):
        self.calls = []

    def query_board_id(self):
        self.calls.append("board")
        return 0x007D

    def query_protocol_version(self):
        self.calls.append("version")
        return 0x0003

    def query_buttons(self):
        self.calls.append("buttons")
        return 0x0010


class ManualClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def test_application_requires_execution_service():
    with pytest.raises(
        TypeError,
        match="must be an ExecutionService",
    ):
        LaboratoryApplication(object())


def test_configuration_defaults():
    configuration = (
        LaboratoryApplicationConfiguration()
    )

    assert (
        configuration.controller_family
        == "A125"
    )
    assert configuration.cooldown_seconds == 1.0
    assert configuration.require_fingerprint is True
    assert configuration.event_history_size == 1000


def test_configuration_requires_controller_family():
    with pytest.raises(
        ValueError,
        match="controller_family is required",
    ):
        LaboratoryApplicationConfiguration(
            controller_family="",
        )


def test_configuration_rejects_negative_cooldown():
    with pytest.raises(
        ValueError,
        match="cooldown_seconds cannot be negative",
    ):
        LaboratoryApplicationConfiguration(
            cooldown_seconds=-1,
        )


def test_configuration_requires_positive_history():
    with pytest.raises(
        ValueError,
        match="event_history_size must be greater",
    ):
        LaboratoryApplicationConfiguration(
            event_history_size=0,
        )


def test_builder_creates_a125_application():
    controller = FakeController()

    application = (
        build_a125_laboratory_application(
            controller
        )
    )

    assert application.controller_family == "A125"
    assert (
        application.execution_service.controller
        is controller
    )
    assert len(application.catalog) == 3


def test_simulation_is_default():
    controller = FakeController()
    application = (
        build_a125_laboratory_application(
            controller
        )
    )

    result = application.execute(
        "board-query"
    )

    assert (
        result.status
        is ExecutionStatus.SIMULATED
    )
    assert controller.calls == []


def test_live_execution_calls_controller():
    controller = FakeController()
    application = (
        build_a125_laboratory_application(
            controller,
            configuration=(
                LaboratoryApplicationConfiguration(
                    cooldown_seconds=0,
                )
            ),
        )
    )

    result = application.execute(
        "version-query",
        live=True,
    )

    assert (
        result.status
        is ExecutionStatus.SUCCEEDED
    )
    assert result.data == 0x0003
    assert controller.calls == ["version"]


def test_execute_live_convenience_method():
    controller = FakeController()
    application = (
        build_a125_laboratory_application(
            controller,
            configuration=(
                LaboratoryApplicationConfiguration(
                    cooldown_seconds=0,
                )
            ),
        )
    )

    result = application.execute_live(
        "button-query"
    )

    assert result.data == 0x0010
    assert controller.calls == ["buttons"]


def test_prepare_uses_requested_mode():
    application = (
        build_a125_laboratory_application(
            FakeController()
        )
    )

    prepared = application.prepare(
        "board-query",
        live=True,
    )

    assert (
        prepared.request.mode
        is ExecutionMode.LIVE
    )


def test_live_flag_must_be_boolean():
    application = (
        build_a125_laboratory_application(
            FakeController()
        )
    )

    with pytest.raises(
        TypeError,
        match="live must be a boolean",
    ):
        application.execute(
            "board-query",
            live="yes",
        )


def test_commands_returns_catalog_summaries():
    application = (
        build_a125_laboratory_application(
            FakeController()
        )
    )

    commands = application.commands()

    assert len(commands) == 3
    assert all(
        isinstance(
            command,
            CatalogCommandSummary,
        )
        for command in commands
    )
    assert tuple(
        command.name
        for command in commands
    ) == (
        "board-query",
        "button-query",
        "version-query",
    )


def test_command_returns_one_summary():
    application = (
        build_a125_laboratory_application(
            FakeController()
        )
    )

    command = application.command(
        "board-query"
    )

    assert command.name == "board-query"
    assert command.opcode_hex == "0x00"
    assert (
        command.safety
        == "documented_read_only"
    )
    assert command.read_only is True


def test_command_summary_serializes():
    application = (
        build_a125_laboratory_application(
            FakeController()
        )
    )

    payload = application.command(
        "version-query"
    ).as_dict()

    assert payload["name"] == "version-query"
    assert payload["opcode_hex"] == "0x07"
    assert payload["category"] == "identity"


def test_unknown_opcode_query():
    application = (
        build_a125_laboratory_application(
            FakeController()
        )
    )

    unknown = application.unknown_opcodes(
        start=0,
        end=8,
    )

    assert unknown == (
        0x01,
        0x02,
        0x03,
        0x04,
        0x05,
        0x08,
    )


def test_execution_emits_recorded_event():
    application = (
        build_a125_laboratory_application(
            FakeController(),
            configuration=(
                LaboratoryApplicationConfiguration(
                    cooldown_seconds=0,
                )
            ),
        )
    )

    application.execute_live(
        "board-query"
    )

    assert len(application.events()) == 1

    event = application.latest_event()

    assert event.command == "board-query"
    assert event.success is True
    assert (
        event.metadata["value_hex"]
        == "0x007D"
    )


def test_simulation_event_is_recorded():
    application = (
        build_a125_laboratory_application(
            FakeController()
        )
    )

    application.simulate(
        "board-query"
    )

    event = application.latest_event()

    assert event.event_type.value == "simulated"
    assert event.mode == "simulation"


def test_events_filter_by_command():
    application = (
        build_a125_laboratory_application(
            FakeController(),
            configuration=(
                LaboratoryApplicationConfiguration(
                    cooldown_seconds=0,
                )
            ),
        )
    )

    application.execute_live(
        "board-query"
    )
    application.execute_live(
        "version-query"
    )
    application.execute_live(
        "board-query"
    )

    assert len(
        application.events_for_command(
            "board-query"
        )
    ) == 2


def test_clear_events():
    application = (
        build_a125_laboratory_application(
            FakeController()
        )
    )

    application.simulate(
        "board-query"
    )
    application.clear_events()

    assert application.events() == ()
    assert application.latest_event() is None


def test_custom_listener_receives_event():
    received = []

    application = (
        build_a125_laboratory_application(
            FakeController(),
            event_listeners=[
                received.append,
            ],
        )
    )

    application.simulate(
        "version-query"
    )

    assert len(received) == 1
    assert (
        received[0].command
        == "version-query"
    )


def test_subscribe_and_unsubscribe():
    received = []

    application = (
        build_a125_laboratory_application(
            FakeController()
        )
    )

    listener = application.subscribe(
        received.append
    )

    application.simulate(
        "board-query"
    )

    assert len(received) == 1
    assert application.unsubscribe(
        listener
    ) is True


def test_shared_cooldown_is_preserved():
    clock = ManualClock()

    application = (
        build_a125_laboratory_application(
            FakeController(),
            configuration=(
                LaboratoryApplicationConfiguration(
                    cooldown_seconds=5,
                )
            ),
            cooldown_clock=clock,
        )
    )

    first = application.execute_live(
        "board-query"
    )
    second = application.execute_live(
        "board-query"
    )

    assert (
        first.status
        is ExecutionStatus.SUCCEEDED
    )
    assert (
        second.status
        is ExecutionStatus.DENIED
    )
    assert application.cooldown_remaining(
        "board-query"
    ) == pytest.approx(5.0)


def test_clear_named_cooldown():
    clock = ManualClock()

    application = (
        build_a125_laboratory_application(
            FakeController(),
            configuration=(
                LaboratoryApplicationConfiguration(
                    cooldown_seconds=5,
                )
            ),
            cooldown_clock=clock,
        )
    )

    application.execute_live(
        "board-query"
    )
    application.clear_cooldown(
        "board-query"
    )

    result = application.execute_live(
        "board-query"
    )

    assert (
        result.status
        is ExecutionStatus.SUCCEEDED
    )


def test_summary():
    application = (
        build_a125_laboratory_application(
            FakeController()
        )
    )

    application.simulate(
        "board-query"
    )

    summary = application.summary()

    assert (
        summary["controller_family"]
        == "A125"
    )
    assert summary["command_count"] == 3
    assert summary["known_opcodes"] == [
        0x00,
        0x06,
        0x07,
    ]
    assert (
        summary["unknown_opcode_count"]
        == 253
    )
    assert summary["event_count"] == 1
    assert summary["cooldown_seconds"] == 1.0
    assert summary["fingerprint_required"] is True


def test_existing_service_can_be_wrapped():
    service = build_a125_execution_service(
        FakeController(),
        cooldown_seconds=0,
    )
    recorder = ExecutionEventRecorder()

    application = LaboratoryApplication(
        service,
        event_recorder=recorder,
    )

    result = application.execute_live(
        "board-query"
    )

    assert result.success is True
    assert recorder.latest().command == (
        "board-query"
    )


def test_recorder_is_not_subscribed_twice():
    service = build_a125_execution_service(
        FakeController()
    )
    recorder = ExecutionEventRecorder()

    service.event_bus.subscribe(
        recorder
    )

    application = LaboratoryApplication(
        service,
        event_recorder=recorder,
    )

    application.simulate(
        "board-query"
    )

    assert len(recorder) == 1
