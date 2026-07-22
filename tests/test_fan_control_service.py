import pytest

from truepanel.hardware.fan_control import (
    FanControlInterlock,
    FanProfile,
)
from truepanel.hardware.fan_service import (
    FanControlService,
)


class FakeClock:
    def __init__(self):
        self.value = 1000.0

    def __call__(self):
        return self.value

    def advance(
        self,
        seconds,
    ):
        self.value += float(
            seconds
        )


class FakeExecutor:
    def __init__(self):
        self.decisions = []
        self.closed = False

    def apply(
        self,
        decision,
    ):
        if self.closed:
            raise RuntimeError(
                "executor closed"
            )

        self.decisions.append(
            decision
        )

    def close(self):
        self.closed = True


def healthy_status():
    return {
        "fan_channels": [
            {
                "number": 1,
                "rpm": 1577,
                "alarm": False,
            },
            {
                "number": 2,
                "rpm": 1516,
                "alarm": False,
            },
            {
                "number": 3,
                "rpm": 0,
                "alarm": True,
            },
        ]
    }


def build_service(
    *,
    timeout=300,
):
    clock = FakeClock()
    executor = FakeExecutor()

    service = FanControlService(
        FanControlInterlock(),
        executor,
        command_timeout=timeout,
        clock=clock,
    )

    return (
        service,
        executor,
        clock,
    )


def test_manual_request_is_applied():
    service, executor, _ = (
        build_service()
    )

    decision = service.request_profile(
        "balanced",
        fan_status=healthy_status(),
        temperatures_c=(51, 41, 47),
    )

    assert decision.accepted
    assert (
        service.active_profile
        is FanProfile.BALANCED
    )
    assert len(
        executor.decisions
    ) == 1


def test_manual_profile_gets_deadman_expiry():
    service, _, clock = (
        build_service(
            timeout=60
        )
    )

    service.request_profile(
        "quiet",
        fan_status=healthy_status(),
        temperatures_c=(51,),
    )

    status = service.status()

    assert (
        status.active_profile
        is FanProfile.QUIET
    )
    assert status.expires_at == (
        clock()
        + 60
    )
    assert status.remaining_seconds == 60


def test_expired_profile_returns_to_automatic():
    service, executor, clock = (
        build_service(
            timeout=30
        )
    )

    service.request_profile(
        "cooling_boost",
        fan_status=healthy_status(),
        temperatures_c=(51,),
    )

    clock.advance(
        31
    )

    decision = service.tick(
        fan_status=healthy_status(),
        temperatures_c=(51,),
    )

    assert decision is not None
    assert decision.force_automatic
    assert (
        service.active_profile
        is FanProfile.AUTOMATIC
    )
    assert len(
        executor.decisions
    ) == 2


def test_healthy_manual_profile_is_not_reapplied():
    service, executor, _ = (
        build_service()
    )

    service.request_profile(
        "balanced",
        fan_status=healthy_status(),
        temperatures_c=(51,),
    )

    result = service.tick(
        fan_status=healthy_status(),
        temperatures_c=(52,),
    )

    assert result is None
    assert len(
        executor.decisions
    ) == 1


def test_stale_manual_telemetry_forces_automatic():
    service, executor, _ = (
        build_service()
    )

    service.request_profile(
        "quiet",
        fan_status=healthy_status(),
        temperatures_c=(51,),
    )

    decision = service.tick(
        fan_status=healthy_status(),
        temperatures_c=(51,),
        telemetry_fresh=False,
    )

    assert decision is not None
    assert decision.force_automatic
    assert (
        service.active_profile
        is FanProfile.AUTOMATIC
    )
    assert len(
        executor.decisions
    ) == 2


def test_emergency_temperature_forces_afterburners():
    service, executor, _ = (
        build_service()
    )

    service.request_profile(
        "balanced",
        fan_status=healthy_status(),
        temperatures_c=(51,),
    )

    decision = service.tick(
        fan_status=healthy_status(),
        temperatures_c=(76,),
    )

    assert decision is not None
    assert (
        decision.effective_profile
        is FanProfile.AFTERBURNERS
    )
    assert (
        service.active_profile
        is FanProfile.AFTERBURNERS
    )
    assert len(
        executor.decisions
    ) == 2


def test_failed_fan_forces_afterburners():
    service, _, _ = (
        build_service()
    )

    service.request_profile(
        "quiet",
        fan_status=healthy_status(),
        temperatures_c=(51,),
    )

    failed = healthy_status()
    failed["fan_channels"][0][
        "rpm"
    ] = 0
    failed["fan_channels"][0][
        "alarm"
    ] = True

    decision = service.tick(
        fan_status=failed,
        temperatures_c=(51,),
    )

    assert decision is not None
    assert (
        service.active_profile
        is FanProfile.AFTERBURNERS
    )


def test_automatic_healthy_state_is_untouched():
    service, executor, _ = (
        build_service()
    )

    result = service.tick(
        fan_status=healthy_status(),
        temperatures_c=(51,),
    )

    assert result is None
    assert executor.decisions == []
    assert (
        service.active_profile
        is FanProfile.AUTOMATIC
    )


def test_automatic_state_can_escalate_to_afterburners():
    service, executor, _ = (
        build_service()
    )

    decision = service.tick(
        fan_status=healthy_status(),
        temperatures_c=(76,),
    )

    assert decision is not None
    assert (
        service.active_profile
        is FanProfile.AFTERBURNERS
    )
    assert len(
        executor.decisions
    ) == 1


def test_afterburners_has_no_deadman_expiry():
    service, executor, clock = (
        build_service(
            timeout=30
        )
    )

    service.request_profile(
        "afterburners",
        fan_status={},
        temperatures_c=(),
        telemetry_fresh=False,
    )

    clock.advance(
        3600
    )

    result = service.tick(
        fan_status={},
        temperatures_c=(),
        telemetry_fresh=False,
    )

    assert result is None
    assert (
        service.active_profile
        is FanProfile.AFTERBURNERS
    )
    assert service.expires_at is None
    assert len(
        executor.decisions
    ) == 1


def test_explicit_automatic_clears_expiry():
    service, executor, _ = (
        build_service()
    )

    service.request_profile(
        "quiet",
        fan_status=healthy_status(),
        temperatures_c=(51,),
    )

    service.request_profile(
        "automatic",
        fan_status={},
        temperatures_c=(),
        telemetry_fresh=False,
    )

    assert (
        service.active_profile
        is FanProfile.AUTOMATIC
    )
    assert service.expires_at is None
    assert len(
        executor.decisions
    ) == 2


def test_shutdown_closes_executor_and_service():
    service, executor, _ = (
        build_service()
    )

    service.shutdown()

    assert executor.closed
    assert service.status().closed
    assert (
        service.active_profile
        is FanProfile.AUTOMATIC
    )


def test_shutdown_is_idempotent():
    service, executor, _ = (
        build_service()
    )

    service.shutdown()
    service.shutdown()

    assert executor.closed


def test_closed_service_rejects_commands():
    service, _, _ = (
        build_service()
    )

    service.shutdown()

    with pytest.raises(
        RuntimeError
    ):
        service.request_profile(
            "balanced",
            fan_status=healthy_status(),
            temperatures_c=(51,),
        )


def test_context_manager_restores_on_exit():
    clock = FakeClock()
    executor = FakeExecutor()

    with FanControlService(
        FanControlInterlock(),
        executor,
        clock=clock,
    ) as service:
        service.request_profile(
            "balanced",
            fan_status=healthy_status(),
            temperatures_c=(51,),
        )

    assert executor.closed
    assert service.status().closed
