from truepanel.host.bootstrap import (
    build_host_agent_bootstrap,
)


class FakeFanRuntime:
    def __init__(self):
        self.service = object()


class FakeHistory:
    def __init__(
        self,
        path,
        *,
        enabled,
    ):
        self.path = path
        self.enabled = enabled


class FakeAuthority:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.operator_armed = False
        self.dry_run = True


def test_bootstrap_owns_host_dependencies():
    runtime = FakeFanRuntime()

    bootstrap = build_host_agent_bootstrap(
        {},
        fan_runtime_factory=lambda config: runtime,
        fan_history_factory=FakeHistory,
        commissioning_history_factory=FakeHistory,
        thermal_authority_factory=FakeAuthority,
    )

    assert bootstrap.fan_runtime is runtime
    assert bootstrap.thermal_authority is not None
    assert bootstrap.fan_control_history is not None
    assert bootstrap.thermal_commissioning_history is not None


def test_bootstrap_starts_thermal_authority_safe():
    runtime = FakeFanRuntime()

    bootstrap = build_host_agent_bootstrap(
        {},
        fan_runtime_factory=lambda config: runtime,
        fan_history_factory=FakeHistory,
        commissioning_history_factory=FakeHistory,
        thermal_authority_factory=FakeAuthority,
    )

    authority = bootstrap.thermal_authority

    assert authority.operator_armed is False
    assert authority.dry_run is True


def test_bootstrap_passes_guarded_fan_service():
    runtime = FakeFanRuntime()

    bootstrap = build_host_agent_bootstrap(
        {},
        fan_runtime_factory=lambda config: runtime,
        fan_history_factory=FakeHistory,
        commissioning_history_factory=FakeHistory,
        thermal_authority_factory=FakeAuthority,
    )

    assert (
        bootstrap.thermal_authority
        .kwargs["service"]
        is runtime.service
    )


def test_bootstrap_preserves_policy_mode():
    runtime = FakeFanRuntime()

    config = {
        "hardware": {
            "thermal_policy": {
                "mode": "automatic_control",
            }
        }
    }

    bootstrap = build_host_agent_bootstrap(
        config,
        fan_runtime_factory=lambda config: runtime,
        fan_history_factory=FakeHistory,
        commissioning_history_factory=FakeHistory,
        thermal_authority_factory=FakeAuthority,
    )

    assert (
        bootstrap.thermal_authority
        .kwargs["policy_mode"]
        == "automatic_control"
    )


def test_bootstrap_invalid_policy_fails_safe():
    runtime = FakeFanRuntime()

    config = {
        "hardware": {
            "thermal_policy": {
                "mode": "warp_factor_nine",
            }
        }
    }

    bootstrap = build_host_agent_bootstrap(
        config,
        fan_runtime_factory=lambda config: runtime,
        fan_history_factory=FakeHistory,
        commissioning_history_factory=FakeHistory,
        thermal_authority_factory=FakeAuthority,
    )

    assert (
        bootstrap.thermal_authority
        .kwargs["policy_mode"]
        == "observe_only"
    )


def test_bootstrap_owns_history_paths():
    runtime = FakeFanRuntime()

    config = {
        "history": {
            "enabled": False,
            "fan_control_path": "/tmp/fan.jsonl",
            "thermal_commissioning_path": (
                "/tmp/thermal.jsonl"
            ),
        }
    }

    bootstrap = build_host_agent_bootstrap(
        config,
        fan_runtime_factory=lambda config: runtime,
        fan_history_factory=FakeHistory,
        commissioning_history_factory=FakeHistory,
        thermal_authority_factory=FakeAuthority,
    )

    assert (
        bootstrap.fan_control_history.path
        == "/tmp/fan.jsonl"
    )

    assert (
        bootstrap.thermal_commissioning_history.path
        == "/tmp/thermal.jsonl"
    )

    assert bootstrap.fan_control_history.enabled is False
    assert (
        bootstrap.thermal_commissioning_history.enabled
        is False
    )


class FakeDecision:
    def __init__(
        self,
        reason,
        *,
        force_automatic=False,
    ):
        self.reason = reason
        self.force_automatic = force_automatic


class RecordingHistory:
    def __init__(self):
        self.events = []

    def append(self, event):
        self.events.append(event)


def test_bootstrap_classifies_safety_event_sources():
    recovery = FakeDecision(
        "Safety recovery confirmed",
        force_automatic=True,
    )
    timeout = FakeDecision(
        "Manual profile expired",
        force_automatic=True,
    )
    safety = FakeDecision(
        "Fan RPM below threshold",
        force_automatic=True,
    )

    from truepanel.host.bootstrap import (
        HostAgentBootstrap,
    )

    assert (
        HostAgentBootstrap.fan_event_source(
            recovery
        )
        == "recovery"
    )

    assert (
        HostAgentBootstrap.fan_event_source(
            timeout
        )
        == "timeout"
    )

    assert (
        HostAgentBootstrap.fan_event_source(
            safety
        )
        == "safety"
    )
