from truepanel.lab.authorization import (
    ExecutionAuthorization,
)
from truepanel.lab.cooldown import CooldownTracker
from truepanel.lab.interlock import (
    DangerLevel,
    ExecutionInterlock,
    ExecutionMode,
    ExecutionRequest,
    InterlockReason,
)


class FakeClock:
    def __init__(self):
        self.value = 10.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


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


def test_safe_simulation_allowed():
    decision = ExecutionInterlock().evaluate(
        make_request()
    )

    assert decision.allowed
    assert decision.simulation_only
    assert (
        decision.reason
        is InterlockReason.SIMULATION_ALLOWED
    )


def test_unknown_opcode_simulation_allowed():
    request = make_request(
        opcode=0x99,
        known_opcode=False,
    )

    decision = ExecutionInterlock().evaluate(
        request
    )

    assert decision.allowed
    assert decision.simulation_only


def test_unknown_opcode_live_denied():
    request = make_request(
        opcode=0x99,
        known_opcode=False,
        mode=ExecutionMode.LIVE,
    )

    decision = ExecutionInterlock().evaluate(
        request,
        controller_family="A125",
    )

    assert not decision.allowed
    assert (
        decision.reason
        is InterlockReason.UNKNOWN_OPCODE
    )


def test_experimental_live_denied():
    request = make_request(
        danger_level=DangerLevel.EXPERIMENTAL,
        mode=ExecutionMode.LIVE,
    )

    decision = ExecutionInterlock().evaluate(
        request,
        controller_family="A125",
    )

    assert not decision.allowed
    assert (
        decision.reason
        is InterlockReason.SIMULATION_REQUIRED
    )


def test_forbidden_operation_always_denied():
    request = make_request(
        danger_level=DangerLevel.FORBIDDEN,
    )

    decision = ExecutionInterlock().evaluate(
        request
    )

    assert not decision.allowed
    assert (
        decision.reason
        is InterlockReason.FORBIDDEN_OPERATION
    )


def test_live_execution_requires_fingerprint():
    request = make_request(
        mode=ExecutionMode.LIVE,
    )

    decision = ExecutionInterlock().evaluate(
        request
    )

    assert not decision.allowed
    assert (
        decision.reason
        is InterlockReason.FINGERPRINT_REQUIRED
    )


def test_fingerprint_mismatch_denied():
    request = make_request(
        mode=ExecutionMode.LIVE,
    )

    decision = ExecutionInterlock().evaluate(
        request,
        controller_family="NOT-A125",
    )

    assert not decision.allowed
    assert (
        decision.reason
        is InterlockReason.FINGERPRINT_MISMATCH
    )


def test_safe_live_execution_allowed():
    request = make_request(
        mode=ExecutionMode.LIVE,
    )

    decision = ExecutionInterlock().evaluate(
        request,
        controller_family="A125",
    )

    assert decision.allowed
    assert not decision.simulation_only


def test_dangerous_live_requires_authorization():
    request = make_request(
        danger_level=DangerLevel.DANGEROUS,
        mode=ExecutionMode.LIVE,
    )

    decision = ExecutionInterlock().evaluate(
        request,
        controller_family="A125",
    )

    assert not decision.allowed
    assert (
        decision.reason
        is InterlockReason.AUTHORIZATION_REQUIRED
    )


def test_dangerous_live_accepts_matching_authorization():
    request = make_request(
        danger_level=DangerLevel.DANGEROUS,
        mode=ExecutionMode.LIVE,
    )
    authorization = ExecutionAuthorization.issue(
        request.request_id
    )

    decision = ExecutionInterlock().evaluate(
        request,
        authorization=authorization,
        controller_family="A125",
    )

    assert decision.allowed


def test_authorization_cannot_be_reused_for_other_request():
    first = make_request(
        danger_level=DangerLevel.DANGEROUS,
        mode=ExecutionMode.LIVE,
    )
    second = make_request(
        danger_level=DangerLevel.DANGEROUS,
        mode=ExecutionMode.LIVE,
    )
    authorization = ExecutionAuthorization.issue(
        first.request_id
    )

    decision = ExecutionInterlock().evaluate(
        second,
        authorization=authorization,
        controller_family="A125",
    )

    assert not decision.allowed
    assert (
        decision.reason
        is InterlockReason.AUTHORIZATION_INVALID
    )


def test_cooldown_blocks_repeated_live_execution():
    clock = FakeClock()
    cooldown = CooldownTracker(
        cooldown_seconds=5,
        clock=clock,
    )
    interlock = ExecutionInterlock(
        cooldown=cooldown,
    )
    request = make_request(
        mode=ExecutionMode.LIVE,
    )

    first = interlock.evaluate(
        request,
        controller_family="A125",
    )
    assert first.allowed

    interlock.record_execution(request)

    second = interlock.evaluate(
        request,
        controller_family="A125",
    )

    assert not second.allowed
    assert (
        second.reason
        is InterlockReason.COOLDOWN_ACTIVE
    )
    assert second.cooldown_remaining == 5.0


def test_cooldown_expires():
    clock = FakeClock()
    cooldown = CooldownTracker(
        cooldown_seconds=5,
        clock=clock,
    )
    interlock = ExecutionInterlock(
        cooldown=cooldown,
    )
    request = make_request(
        mode=ExecutionMode.LIVE,
    )

    interlock.record_execution(request)
    clock.advance(5)

    decision = interlock.evaluate(
        request,
        controller_family="A125",
    )

    assert decision.allowed


def test_requires_live_hardware_rejects_simulation():
    request = make_request(
        requires_live_hardware=True,
    )

    decision = ExecutionInterlock().evaluate(
        request
    )

    assert not decision.allowed
    assert (
        decision.reason
        is InterlockReason.LIVE_MODE_REQUIRED
    )
