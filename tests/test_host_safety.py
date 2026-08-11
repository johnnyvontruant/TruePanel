from truepanel.host.safety import (
    HostAgentSafetyCoordinator,
)


class FakeDecision:
    reason = "test"


class FakeService:
    def __init__(self):
        self.requests = []

    def request_profile(
        self,
        profile,
        **kwargs,
    ):
        self.requests.append(
            (
                profile,
                kwargs,
            )
        )
        return FakeDecision()


class FakeRuntime:
    def __init__(
        self,
        *,
        active_profile="balanced",
        authority="manual",
    ):
        self.service = FakeService()
        self.active_profile = active_profile
        self.authority = authority

    def status_payload(self):
        return {
            "active_profile": (
                self.active_profile
            ),
            "control_authority": (
                self.authority
            ),
        }


def telemetry():
    return {
        "fan_status": {
            "fan_channels": [],
        },
        "temperatures_c": (
            42.0,
            43.0,
        ),
        "telemetry_fresh": True,
    }


def test_restore_automatic_uses_guarded_runtime():
    runtime = FakeRuntime()

    coordinator = HostAgentSafetyCoordinator(
        fan_runtime=runtime,
        telemetry_provider=telemetry,
    )

    decision = coordinator.restore_automatic(
        "restore test"
    )

    assert isinstance(
        decision,
        FakeDecision,
    )

    assert len(
        runtime.service.requests
    ) == 1

    profile, kwargs = (
        runtime.service.requests[0]
    )

    assert profile == "automatic"
    assert kwargs["telemetry_fresh"] is True

    assert kwargs[
        "temperatures_c"
    ] == (
        42.0,
        43.0,
    )


def test_restore_skips_when_already_automatic():
    runtime = FakeRuntime(
        active_profile="automatic",
        authority="automatic",
    )

    coordinator = HostAgentSafetyCoordinator(
        fan_runtime=runtime,
        telemetry_provider=telemetry,
    )

    assert (
        coordinator.restore_automatic(
            "already safe"
        )
        is None
    )

    assert runtime.service.requests == []


def test_restore_records_authoritative_source():
    runtime = FakeRuntime()
    events = []

    coordinator = HostAgentSafetyCoordinator(
        fan_runtime=runtime,
        telemetry_provider=telemetry,
        event_recorder=(
            lambda decision, payload, source: (
                events.append(
                    (
                        decision,
                        payload,
                        source,
                    )
                )
            )
        ),
    )

    coordinator.restore_automatic(
        "restore"
    )

    assert len(events) == 1
    assert events[0][2] == (
        "thermal_policy"
    )


def test_restore_publishes_reason():
    runtime = FakeRuntime()
    reasons = []

    def publish(
        reason=None,
    ):
        reasons.append(reason)

    coordinator = HostAgentSafetyCoordinator(
        fan_runtime=runtime,
        telemetry_provider=telemetry,
        status_publisher=publish,
    )

    coordinator.restore_automatic(
        "safety restoration"
    )

    assert reasons == [
        "safety restoration"
    ]


def test_manual_event_source_is_preserved():
    runtime = FakeRuntime()
    events = []

    coordinator = HostAgentSafetyCoordinator(
        fan_runtime=runtime,
        telemetry_provider=telemetry,
        event_recorder=(
            lambda decision, payload, source: (
                events.append(source)
            )
        ),
    )

    coordinator.record_event(
        FakeDecision(),
        telemetry(),
        source="manual",
    )

    assert events == [
        "manual"
    ]


def test_missing_thermal_handler_fails_closed():
    coordinator = HostAgentSafetyCoordinator(
        fan_runtime=FakeRuntime(),
        telemetry_provider=telemetry,
    )

    result = (
        coordinator
        .handle_thermal_control(
            "arm"
        )
    )

    assert result["ok"] is False
    assert (
        result["status"]
        == "thermal_control_unavailable"
    )
