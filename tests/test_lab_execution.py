import pytest

from truepanel.lab.authorization import (
    ExecutionAuthorization,
)
from truepanel.lab.cooldown import CooldownTracker
from truepanel.lab.execution import (
    AdapterResponse,
    CallableExecutionAdapter,
    ExecutionAdapter,
    ExecutionEngine,
    ExecutionStatus,
)
from truepanel.lab.interlock import (
    DangerLevel,
    ExecutionInterlock,
    ExecutionMode,
    ExecutionRequest,
    InterlockReason,
)


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        current = self.value
        self.value += 0.025
        return current


class ManualClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class RecordingAdapter(ExecutionAdapter):
    def __init__(
        self,
        response=None,
        error=None,
    ):
        self.response = response
        self.error = error
        self.requests = []

    def execute(self, request):
        self.requests.append(request)

        if self.error is not None:
            raise self.error

        return self.response


def make_request(**overrides):
    values = {
        "opcode": 0x01,
        "name": "board-query",
        "danger_level": DangerLevel.SAFE,
        "mode": ExecutionMode.SIMULATION,
        "known_opcode": True,
    }
    values.update(overrides)

    return ExecutionRequest(**values)


def test_adapter_interface_requires_implementation():
    adapter = ExecutionAdapter()

    with pytest.raises(NotImplementedError):
        adapter.execute(make_request())


def test_engine_requires_interlock():
    with pytest.raises(ValueError):
        ExecutionEngine(
            None,
            RecordingAdapter(),
        )


def test_engine_requires_adapter():
    with pytest.raises(ValueError):
        ExecutionEngine(
            ExecutionInterlock(),
            None,
        )


def test_simulation_does_not_invoke_adapter():
    adapter = RecordingAdapter()
    engine = ExecutionEngine(
        ExecutionInterlock(),
        adapter,
    )

    result = engine.execute(make_request())

    assert result.status is ExecutionStatus.SIMULATED
    assert result.success is True
    assert result.simulated
    assert adapter.requests == []


def test_simulation_contains_request_details():
    adapter = RecordingAdapter()
    engine = ExecutionEngine(
        ExecutionInterlock(),
        adapter,
    )
    request = make_request(
        opcode=0x4D,
        payload=b"\x01\x02",
    )

    result = engine.execute(request)

    assert result.data == {
        "simulated": True,
        "opcode": 0x4D,
        "payload": "0102",
    }


def test_denied_request_does_not_invoke_adapter():
    adapter = RecordingAdapter()
    engine = ExecutionEngine(
        ExecutionInterlock(),
        adapter,
    )
    request = make_request(
        opcode=0x99,
        known_opcode=False,
        mode=ExecutionMode.LIVE,
    )

    result = engine.execute(
        request,
        controller_family="A125",
    )

    assert result.status is ExecutionStatus.DENIED
    assert result.success is False
    assert result.denied
    assert (
        result.decision.reason
        is InterlockReason.UNKNOWN_OPCODE
    )
    assert adapter.requests == []


def test_safe_live_request_invokes_adapter_once():
    adapter = RecordingAdapter(
        response={"board_id": "0x007D"}
    )
    engine = ExecutionEngine(
        ExecutionInterlock(),
        adapter,
    )
    request = make_request(
        mode=ExecutionMode.LIVE,
    )

    result = engine.execute(
        request,
        controller_family="A125",
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.success is True
    assert result.executed_live
    assert result.data == {
        "board_id": "0x007D",
    }
    assert adapter.requests == [request]


def test_adapter_response_preserves_capture_metadata():
    response = AdapterResponse(
        data=b"\x53\x01\x00",
        capture_path=(
            "development/logs/execution.log"
        ),
        metadata={
            "latency_ms": 50.4,
            "response_bytes": 3,
        },
    )
    adapter = RecordingAdapter(response=response)
    engine = ExecutionEngine(
        ExecutionInterlock(),
        adapter,
    )
    request = make_request(
        mode=ExecutionMode.LIVE,
    )

    result = engine.execute(
        request,
        controller_family="A125",
    )

    assert result.data == b"\x53\x01\x00"
    assert result.capture_path.endswith(
        "execution.log"
    )
    assert result.metadata["latency_ms"] == 50.4
    assert result.metadata["response_bytes"] == 3


def test_adapter_exception_becomes_failed_result():
    adapter = RecordingAdapter(
        error=TimeoutError(
            "controller did not respond"
        )
    )
    engine = ExecutionEngine(
        ExecutionInterlock(),
        adapter,
    )
    request = make_request(
        mode=ExecutionMode.LIVE,
    )

    result = engine.execute(
        request,
        controller_family="A125",
    )

    assert result.status is ExecutionStatus.FAILED
    assert result.success is False
    assert result.executed_live
    assert result.error == (
        "controller did not respond"
    )
    assert (
        result.metadata["exception_type"]
        == "TimeoutError"
    )


def test_failed_execution_does_not_start_cooldown():
    cooldown_clock = ManualClock()
    cooldown = CooldownTracker(
        cooldown_seconds=10,
        clock=cooldown_clock,
    )
    interlock = ExecutionInterlock(
        cooldown=cooldown,
    )
    adapter = RecordingAdapter(
        error=RuntimeError("failure")
    )
    engine = ExecutionEngine(
        interlock,
        adapter,
    )
    request = make_request(
        mode=ExecutionMode.LIVE,
    )

    result = engine.execute(
        request,
        controller_family="A125",
    )

    assert result.status is ExecutionStatus.FAILED
    assert cooldown.ready(
        ("A125", request.opcode)
    )


def test_successful_execution_starts_cooldown():
    cooldown_clock = ManualClock()
    cooldown = CooldownTracker(
        cooldown_seconds=10,
        clock=cooldown_clock,
    )
    interlock = ExecutionInterlock(
        cooldown=cooldown,
    )
    adapter = RecordingAdapter(
        response="ok"
    )
    engine = ExecutionEngine(
        interlock,
        adapter,
    )
    request = make_request(
        mode=ExecutionMode.LIVE,
    )

    first = engine.execute(
        request,
        controller_family="A125",
    )
    second = engine.execute(
        request,
        controller_family="A125",
    )

    assert first.status is ExecutionStatus.SUCCEEDED
    assert second.status is ExecutionStatus.DENIED
    assert (
        second.decision.reason
        is InterlockReason.COOLDOWN_ACTIVE
    )
    assert len(adapter.requests) == 1


def test_dangerous_live_request_needs_authorization():
    adapter = RecordingAdapter(response="ok")
    engine = ExecutionEngine(
        ExecutionInterlock(),
        adapter,
    )
    request = make_request(
        danger_level=DangerLevel.DANGEROUS,
        mode=ExecutionMode.LIVE,
    )

    result = engine.execute(
        request,
        controller_family="A125",
    )

    assert result.status is ExecutionStatus.DENIED
    assert adapter.requests == []


def test_dangerous_live_request_executes_when_authorized():
    adapter = RecordingAdapter(response="ok")
    engine = ExecutionEngine(
        ExecutionInterlock(),
        adapter,
    )
    request = make_request(
        danger_level=DangerLevel.DANGEROUS,
        mode=ExecutionMode.LIVE,
    )
    authorization = ExecutionAuthorization.issue(
        request.request_id
    )

    result = engine.execute(
        request,
        authorization=authorization,
        controller_family="A125",
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert adapter.requests == [request]


def test_callable_adapter_wraps_callable():
    calls = []

    def executor(request):
        calls.append(request.opcode)
        return "callable-result"

    adapter = CallableExecutionAdapter(executor)
    engine = ExecutionEngine(
        ExecutionInterlock(),
        adapter,
    )
    request = make_request(
        mode=ExecutionMode.LIVE,
    )

    result = engine.execute(
        request,
        controller_family="A125",
    )

    assert result.data == "callable-result"
    assert calls == [0x01]


def test_duration_is_recorded():
    adapter = RecordingAdapter(response="ok")
    engine = ExecutionEngine(
        ExecutionInterlock(),
        adapter,
        clock=FakeClock(),
    )
    request = make_request(
        mode=ExecutionMode.LIVE,
    )

    result = engine.execute(
        request,
        controller_family="A125",
    )

    assert result.duration_ms == pytest.approx(
        25.0
    )


def test_result_serializes():
    adapter = RecordingAdapter(response="ok")
    engine = ExecutionEngine(
        ExecutionInterlock(),
        adapter,
    )
    request = make_request(
        mode=ExecutionMode.LIVE,
    )

    result = engine.execute(
        request,
        controller_family="A125",
    )
    payload = result.as_dict()

    assert payload["request_id"] == request.request_id
    assert payload["command"] == "board-query"
    assert payload["opcode"] == 0x01
    assert payload["status"] == "succeeded"
    assert payload["success"] is True
    assert payload["decision"] == "allowed"
