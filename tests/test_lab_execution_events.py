from datetime import UTC, datetime

import pytest

from truepanel.lab.execution import (
    ExecutionResult,
    ExecutionStatus,
)
from truepanel.lab.execution_events import (
    CallableExecutionEventListener,
    ExecutionEvent,
    ExecutionEventBus,
    ExecutionEventListener,
    ExecutionEventRecorder,
    ExecutionEventType,
)
from truepanel.lab.interlock import (
    InterlockDecision,
    InterlockReason,
)


def make_result(
    *,
    status=ExecutionStatus.SUCCEEDED,
    success=True,
    command="board-query",
    opcode=0x00,
    metadata=None,
    error="",
):
    return ExecutionResult(
        request_id="request-1",
        command=command,
        opcode=opcode,
        status=status,
        success=success,
        duration_ms=12.5,
        decision=InterlockDecision.allow(
            message="Live execution allowed",
        ),
        data=0x007D,
        capture_path="capture.log",
        metadata=metadata or {
            "mode": "live",
        },
        error=error,
    )


def make_event(**overrides):
    values = {
        "result": make_result(),
        "controller_family": "A125",
        "timestamp": datetime(
            2026,
            7,
            14,
            tzinfo=UTC,
        ),
    }
    values.update(overrides)

    return ExecutionEvent.from_result(
        **values
    )


def test_event_from_successful_result():
    event = make_event()

    assert (
        event.event_type
        is ExecutionEventType.SUCCEEDED
    )
    assert event.command == "board-query"
    assert event.opcode == 0x00
    assert event.opcode_hex == "0x00"
    assert event.controller_family == "A125"
    assert event.mode == "live"
    assert event.success is True
    assert event.data == 0x007D


def test_event_from_denied_result():
    result = ExecutionResult(
        request_id="request-2",
        command="unknown",
        opcode=0x99,
        status=ExecutionStatus.DENIED,
        success=False,
        duration_ms=1.0,
        decision=InterlockDecision.deny(
            InterlockReason.UNKNOWN_OPCODE,
            "Unknown opcode denied",
        ),
        metadata={
            "mode": "live",
        },
        error="Unknown opcode denied",
    )

    event = ExecutionEvent.from_result(
        result,
        controller_family="A125",
    )

    assert (
        event.event_type
        is ExecutionEventType.DENIED
    )
    assert event.success is False
    assert event.decision == "unknown_opcode"
    assert event.error == "Unknown opcode denied"


def test_event_copies_metadata():
    metadata = {
        "mode": "live",
        "value_hex": "0x007D",
    }

    event = make_event(
        result=make_result(
            metadata=metadata
        )
    )

    metadata["value_hex"] = "changed"

    assert (
        event.metadata["value_hex"]
        == "0x007D"
    )


def test_event_serializes():
    event = make_event()

    payload = event.as_dict()

    assert payload["timestamp"] == (
        "2026-07-14T00:00:00+00:00"
    )
    assert payload["event_type"] == "succeeded"
    assert payload["opcode_hex"] == "0x00"
    assert payload["controller_family"] == "A125"


def test_result_is_required():
    with pytest.raises(
        TypeError,
        match="must be an ExecutionResult",
    ):
        ExecutionEvent.from_result(
            object(),
            controller_family="A125",
        )


def test_controller_family_is_required():
    with pytest.raises(
        ValueError,
        match="controller_family is required",
    ):
        ExecutionEvent.from_result(
            make_result(),
            controller_family="",
        )


def test_listener_interface_requires_implementation():
    listener = ExecutionEventListener()

    with pytest.raises(NotImplementedError):
        listener.handle(make_event())


def test_callable_listener_receives_event():
    events = []

    listener = CallableExecutionEventListener(
        events.append
    )

    event = make_event()
    listener.handle(event)

    assert events == [event]


def test_callable_listener_requires_callable():
    with pytest.raises(
        TypeError,
        match="callback must be callable",
    ):
        CallableExecutionEventListener(
            object()
        )


def test_bus_publishes_to_listener():
    recorder = ExecutionEventRecorder()
    bus = ExecutionEventBus([recorder])

    event = make_event()
    failures = bus.publish(event)

    assert failures == ()
    assert recorder.events == (event,)


def test_bus_accepts_callable():
    events = []
    bus = ExecutionEventBus(
        [events.append]
    )

    event = make_event()
    bus.publish(event)

    assert events == [event]


def test_bus_rejects_invalid_listener():
    with pytest.raises(
        TypeError,
        match="listener must be",
    ):
        ExecutionEventBus(
            [object()]
        )


def test_bus_rejects_invalid_event():
    bus = ExecutionEventBus()

    with pytest.raises(
        TypeError,
        match="must be an ExecutionEvent",
    ):
        bus.publish(object())


def test_listener_failure_is_isolated():
    recorder = ExecutionEventRecorder()

    def broken_listener(event):
        raise RuntimeError(
            "listener exploded"
        )

    bus = ExecutionEventBus(
        [
            broken_listener,
            recorder,
        ]
    )

    event = make_event()
    failures = bus.publish(event)

    assert recorder.events == (event,)
    assert len(failures) == 1
    assert (
        failures[0]["exception_type"]
        == "RuntimeError"
    )
    assert (
        failures[0]["error"]
        == "listener exploded"
    )


def test_unsubscribe():
    recorder = ExecutionEventRecorder()
    bus = ExecutionEventBus(
        [recorder]
    )

    assert bus.unsubscribe(recorder) is True
    assert bus.unsubscribe(recorder) is False
    assert len(bus) == 0


def test_recorder_enforces_max_events():
    recorder = ExecutionEventRecorder(
        max_events=2
    )

    recorder.handle(
        make_event(
            result=make_result(
                command="first",
                opcode=0x01,
            )
        )
    )
    recorder.handle(
        make_event(
            result=make_result(
                command="second",
                opcode=0x02,
            )
        )
    )
    recorder.handle(
        make_event(
            result=make_result(
                command="third",
                opcode=0x03,
            )
        )
    )

    assert tuple(
        event.command
        for event in recorder.events
    ) == (
        "second",
        "third",
    )


def test_recorder_latest():
    recorder = ExecutionEventRecorder()

    assert recorder.latest() is None

    event = make_event()
    recorder.handle(event)

    assert recorder.latest() is event


def test_recorder_filters_by_command():
    recorder = ExecutionEventRecorder()

    recorder.handle(
        make_event()
    )
    recorder.handle(
        make_event(
            result=make_result(
                command="version-query",
                opcode=0x07,
            )
        )
    )
    recorder.handle(
        make_event()
    )

    assert len(
        recorder.by_command(
            "board-query"
        )
    ) == 2


def test_recorder_filters_failures():
    recorder = ExecutionEventRecorder()

    recorder.handle(
        make_event()
    )
    recorder.handle(
        make_event(
            result=make_result(
                status=ExecutionStatus.FAILED,
                success=False,
                error="timeout",
            )
        )
    )

    failures = recorder.failures()

    assert len(failures) == 1
    assert failures[0].error == "timeout"


def test_recorder_serializes():
    recorder = ExecutionEventRecorder()
    recorder.handle(make_event())

    payload = recorder.as_dict()

    assert payload["event_count"] == 1
    assert (
        payload["events"][0]["command"]
        == "board-query"
    )


def test_recorder_clear():
    recorder = ExecutionEventRecorder()
    recorder.handle(make_event())

    recorder.clear()

    assert len(recorder) == 0


def test_recorder_requires_positive_limit():
    with pytest.raises(
        ValueError,
        match="must be greater than zero",
    ):
        ExecutionEventRecorder(
            max_events=0
        )
