from datetime import UTC, datetime

import pytest

from truepanel.lab.catalog import (
    CommandCatalog,
    CommandCategory,
    CommandSafety,
    LabCommand,
)
from truepanel.lab.execution import ExecutionStatus
from truepanel.lab.execution_service import (
    ExecutionService,
    ExecutionServiceConfiguration,
    PreparedExecution,
    build_a125_execution_service,
)
from truepanel.lab.interlock import (
    DangerLevel,
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


def test_service_requires_controller():
    with pytest.raises(
        ValueError,
        match="controller is required",
    ):
        ExecutionService(None)


def test_configuration_defaults():
    configuration = ExecutionServiceConfiguration()

    assert configuration.controller_family == "A125"
    assert configuration.cooldown_seconds == 1.0
    assert configuration.require_fingerprint is True


def test_configuration_requires_controller_family():
    with pytest.raises(
        ValueError,
        match="controller_family is required",
    ):
        ExecutionServiceConfiguration(
            controller_family="",
        )


def test_configuration_rejects_negative_cooldown():
    with pytest.raises(
        ValueError,
        match="cooldown_seconds cannot be negative",
    ):
        ExecutionServiceConfiguration(
            cooldown_seconds=-1,
        )


def test_prepare_builds_catalog_request():
    service = build_a125_execution_service(
        FakeController()
    )

    prepared = service.prepare(
        "board-query"
    )

    assert isinstance(
        prepared,
        PreparedExecution,
    )
    assert prepared.command == "board-query"
    assert prepared.request.opcode == 0x00
    assert (
        prepared.mode
        is ExecutionMode.SIMULATION
    )
    assert prepared.request.known_opcode is True


def test_prepared_execution_serializes():
    service = build_a125_execution_service(
        FakeController()
    )

    prepared = service.prepare(
        "version-query",
        mode=ExecutionMode.LIVE,
    )

    payload = prepared.as_dict()

    assert payload["command"] == "version-query"
    assert payload["opcode_hex"] == "0x07"
    assert payload["mode"] == "live"
    assert payload["known_opcode"] is True


def test_simulation_does_not_call_controller():
    controller = FakeController()
    service = build_a125_execution_service(
        controller
    )

    result = service.simulate(
        "board-query"
    )

    assert (
        result.status
        is ExecutionStatus.SIMULATED
    )
    assert result.success is True
    assert controller.calls == []


def test_live_board_query():
    controller = FakeController()
    service = build_a125_execution_service(
        controller
    )

    result = service.execute_live(
        "board-query"
    )

    assert (
        result.status
        is ExecutionStatus.SUCCEEDED
    )
    assert result.data == 0x007D
    assert controller.calls == ["board"]


def test_live_version_query():
    controller = FakeController()
    service = build_a125_execution_service(
        controller
    )

    result = service.execute_live(
        "version-query"
    )

    assert result.data == 0x0003
    assert controller.calls == ["version"]


def test_live_button_query():
    controller = FakeController()
    service = build_a125_execution_service(
        controller
    )

    result = service.execute_live(
        "button-query"
    )

    assert result.data == 0x0010
    assert controller.calls == ["buttons"]


def test_wrong_fingerprint_is_denied():
    controller = FakeController()
    service = build_a125_execution_service(
        controller
    )

    result = service.execute_live(
        "board-query",
        controller_family="OTHER",
    )

    assert (
        result.status
        is ExecutionStatus.DENIED
    )
    assert controller.calls == []


def test_shared_cooldown_blocks_second_call():
    clock = ManualClock()
    controller = FakeController()
    service = build_a125_execution_service(
        controller,
        cooldown_seconds=5,
        cooldown_clock=clock,
    )

    first = service.execute_live(
        "board-query"
    )
    second = service.execute_live(
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
    assert controller.calls == ["board"]
    assert service.cooldown_remaining(
        "board-query"
    ) == pytest.approx(5.0)


def test_different_commands_have_independent_cooldowns():
    clock = ManualClock()
    controller = FakeController()
    service = build_a125_execution_service(
        controller,
        cooldown_seconds=5,
        cooldown_clock=clock,
    )

    first = service.execute_live(
        "board-query"
    )
    second = service.execute_live(
        "version-query"
    )

    assert (
        first.status
        is ExecutionStatus.SUCCEEDED
    )
    assert (
        second.status
        is ExecutionStatus.SUCCEEDED
    )
    assert controller.calls == [
        "board",
        "version",
    ]


def test_cooldown_expires():
    clock = ManualClock()
    controller = FakeController()
    service = build_a125_execution_service(
        controller,
        cooldown_seconds=5,
        cooldown_clock=clock,
    )

    service.execute_live(
        "board-query"
    )
    clock.advance(5)

    result = service.execute_live(
        "board-query"
    )

    assert (
        result.status
        is ExecutionStatus.SUCCEEDED
    )
    assert controller.calls == [
        "board",
        "board",
    ]


def test_clear_named_cooldown():
    clock = ManualClock()
    controller = FakeController()
    service = build_a125_execution_service(
        controller,
        cooldown_seconds=5,
        cooldown_clock=clock,
    )

    service.execute_live(
        "board-query"
    )
    service.clear_cooldown(
        "board-query"
    )

    result = service.execute_live(
        "board-query"
    )

    assert (
        result.status
        is ExecutionStatus.SUCCEEDED
    )


def test_authorization_is_bound_to_prepared_request():
    command = LabCommand(
        name="danger-query",
        opcode=0x20,
        category=CommandCategory.DIAGNOSTIC,
        safety=CommandSafety.DOCUMENTED_READ_ONLY,
        danger_level=DangerLevel.DANGEROUS,
        handler_name="query_board_id",
        description="Synthetic dangerous read-only query.",
        documented=True,
        read_only=True,
    )

    catalog = CommandCatalog([command])
    controller = FakeController()

    service = ExecutionService(
        controller,
        catalog=catalog,
        configuration=ExecutionServiceConfiguration(
            controller_family="TEST",
            cooldown_seconds=0,
        ),
    )

    prepared = service.prepare(
        "danger-query",
        mode=ExecutionMode.LIVE,
    )

    authorization = service.authorize(
        prepared,
        operator="test-operator",
        now=datetime.now(UTC),
    )

    result = service.execute_prepared(
        prepared,
        authorization=authorization,
    )

    assert (
        result.status
        is ExecutionStatus.SUCCEEDED
    )
    assert controller.calls == ["board"]


def test_authorization_for_other_request_is_rejected():
    command = LabCommand(
        name="danger-query",
        opcode=0x20,
        category=CommandCategory.DIAGNOSTIC,
        safety=CommandSafety.DOCUMENTED_READ_ONLY,
        danger_level=DangerLevel.DANGEROUS,
        handler_name="query_board_id",
        description="Synthetic dangerous read-only query.",
        documented=True,
        read_only=True,
    )

    catalog = CommandCatalog([command])
    controller = FakeController()

    service = ExecutionService(
        controller,
        catalog=catalog,
        configuration=ExecutionServiceConfiguration(
            controller_family="TEST",
            cooldown_seconds=0,
        ),
    )

    first = service.prepare(
        "danger-query",
        mode=ExecutionMode.LIVE,
    )
    second = service.prepare(
        "danger-query",
        mode=ExecutionMode.LIVE,
    )

    authorization = service.authorize(
        first
    )

    result = service.execute_prepared(
        second,
        authorization=authorization,
    )

    assert (
        result.status
        is ExecutionStatus.DENIED
    )
    assert controller.calls == []


def test_authorize_accepts_raw_request():
    service = build_a125_execution_service(
        FakeController()
    )

    prepared = service.prepare(
        "board-query"
    )

    authorization = service.authorize(
        prepared.request,
        operator="operator",
    )

    assert authorization.request_id == (
        prepared.request_id
    )
    assert authorization.operator == "operator"


def test_execute_prepared_rejects_invalid_object():
    service = build_a125_execution_service(
        FakeController()
    )

    with pytest.raises(
        TypeError,
        match="prepared must be",
    ):
        service.execute_prepared(object())


def test_factory_helper_uses_a125_defaults():
    service = build_a125_execution_service(
        FakeController(),
        cooldown_seconds=2.5,
        require_fingerprint=False,
    )

    assert service.controller_family == "A125"
    assert service.cooldown.cooldown_seconds == 2.5
    assert service.interlock.require_fingerprint is False


def test_service_exposes_shared_components():
    controller = FakeController()
    service = build_a125_execution_service(
        controller
    )

    assert service.controller is controller
    assert service.request_factory.catalog is (
        service.catalog
    )
    assert service.adapter.catalog is (
        service.catalog
    )
    assert service.engine.interlock is (
        service.interlock
    )
    assert service.engine.adapter is (
        service.adapter
    )


def test_service_emits_execution_event():
    from truepanel.lab.execution_events import (
        ExecutionEventBus,
        ExecutionEventRecorder,
        ExecutionEventType,
    )

    recorder = ExecutionEventRecorder()
    bus = ExecutionEventBus(
        [recorder]
    )

    service = build_a125_execution_service(
        FakeController(),
        cooldown_seconds=0,
        event_bus=bus,
    )

    result = service.execute_live(
        "board-query"
    )

    assert result.success is True
    assert len(recorder) == 1

    event = recorder.latest()

    assert (
        event.event_type
        is ExecutionEventType.SUCCEEDED
    )
    assert event.command == "board-query"
    assert event.controller_family == "A125"
    assert event.metadata["value_hex"] == "0x007D"


def test_service_emits_denied_event():
    from truepanel.lab.execution_events import (
        ExecutionEventBus,
        ExecutionEventRecorder,
        ExecutionEventType,
    )

    recorder = ExecutionEventRecorder()

    service = build_a125_execution_service(
        FakeController(),
        event_bus=ExecutionEventBus(
            [recorder]
        ),
    )

    result = service.execute_live(
        "board-query",
        controller_family="OTHER",
    )

    assert result.success is False
    assert len(recorder) == 1
    assert (
        recorder.latest().event_type
        is ExecutionEventType.DENIED
    )


def test_event_listener_failure_does_not_change_result():
    from truepanel.lab.execution_events import (
        ExecutionEventBus,
    )

    def broken_listener(event):
        raise RuntimeError(
            "telemetry failure"
        )

    service = build_a125_execution_service(
        FakeController(),
        cooldown_seconds=0,
        event_bus=ExecutionEventBus(
            [broken_listener]
        ),
    )

    result = service.execute_live(
        "board-query"
    )

    assert result.success is True
    assert (
        result.status
        is ExecutionStatus.SUCCEEDED
    )


def test_service_uses_supplied_event_bus():
    from truepanel.lab.execution_events import (
        ExecutionEventBus,
    )

    bus = ExecutionEventBus()

    service = build_a125_execution_service(
        FakeController(),
        event_bus=bus,
    )

    assert service.event_bus is bus
