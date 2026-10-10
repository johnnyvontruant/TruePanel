"""Bounded, no-actuation startup handling for a delayed Fintek sysfs device."""

from dataclasses import dataclass

from truepanel.host.bootstrap import build_host_agent_bootstrap


@dataclass
class FakeRuntime:
    enabled: bool = True
    service: object | None = None
    unavailable_reason: str | None = None


class FakeHistory:
    def __init__(self, path, *, enabled):
        self.path = path
        self.enabled = enabled


class FakeAuthority:
    def __init__(self, **kwargs):
        self.service = kwargs["service"]
        self.operator_armed = False
        self.dry_run = True


def build_with_factory(factory, sleep):
    return build_host_agent_bootstrap(
        {},
        fan_runtime_factory=factory,
        fan_startup_sleep=sleep,
        fan_history_factory=FakeHistory,
        commissioning_history_factory=FakeHistory,
        thermal_authority_factory=FakeAuthority,
    )


def test_delayed_fintek_recovers_before_authority_is_wired():
    unavailable = FakeRuntime(
        unavailable_reason="Fintek fan controller is unavailable."
    )
    connected_service = object()
    connected = FakeRuntime(service=connected_service)
    responses = iter([unavailable, unavailable, connected])
    events = []

    def factory(config):
        assert config == {}
        events.append("discover")
        return next(responses)

    def sleeper(seconds):
        events.append(("sleep", seconds))

    bootstrap = build_with_factory(factory, sleeper)

    assert events == [
        "discover", ("sleep", 1.0), "discover",
        ("sleep", 1.0), "discover",
    ]
    assert bootstrap.fan_runtime is connected
    assert bootstrap.thermal_authority.service is connected_service
    assert bootstrap.thermal_authority.operator_armed is False
    assert bootstrap.thermal_authority.dry_run is True


def test_missing_fintek_exhausts_retries_and_stays_disconnected():
    runtime = FakeRuntime(
        unavailable_reason="Fintek fan controller is unavailable."
    )
    calls = []
    bootstrap = build_with_factory(
        lambda config: (calls.append("discover") or runtime),
        lambda seconds: calls.append(("sleep", seconds)),
    )

    assert len([item for item in calls if item == "discover"]) == 4
    assert len([item for item in calls if item == ("sleep", 1.0)]) == 3
    assert bootstrap.fan_runtime is runtime
    assert bootstrap.thermal_authority.service is None


def test_other_errors_do_not_retry_or_mask_failure():
    runtime = FakeRuntime(
        unavailable_reason="Fan control connection failed: PermissionError"
    )
    calls = []
    bootstrap = build_with_factory(
        lambda config: (calls.append("discover") or runtime),
        lambda seconds: calls.append("sleep"),
    )

    assert calls == ["discover"]
    assert bootstrap.fan_runtime is runtime


def test_disabled_controller_never_retries():
    runtime = FakeRuntime(
        enabled=False,
        unavailable_reason="Fintek fan controller is unavailable.",
    )
    calls = []
    bootstrap = build_with_factory(
        lambda config: (calls.append("discover") or runtime),
        lambda seconds: calls.append("sleep"),
    )

    assert calls == ["discover"]
    assert bootstrap.fan_runtime is runtime
