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


class FakeTelemetry:
    def __init__(
        self,
        *,
        temperature_provider,
        fan_status_provider,
    ):
        self.temperature_provider = temperature_provider
        self.fan_status_provider = fan_status_provider

    def snapshot(self):
        return {
            "telemetry_fresh": True,
        }


class FakeStatusBridge:
    pass


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


def test_bootstrap_owns_production_telemetry():
    runtime = FakeFanRuntime()
    temperature_provider = object()
    fan_status_provider = lambda: {}

    bootstrap = build_host_agent_bootstrap(
        {},
        fan_runtime_factory=lambda config: runtime,
        fan_history_factory=FakeHistory,
        commissioning_history_factory=FakeHistory,
        thermal_authority_factory=FakeAuthority,
        drive_temperature_provider_factory=(
            lambda: temperature_provider
        ),
        fan_status_provider=fan_status_provider,
        telemetry_factory=FakeTelemetry,
    )

    assert isinstance(bootstrap.telemetry, FakeTelemetry)
    assert (
        bootstrap.telemetry.temperature_provider
        is temperature_provider
    )
    assert (
        bootstrap.telemetry.fan_status_provider
        is fan_status_provider
    )


def test_bootstrap_owns_status_bridge():
    runtime = FakeFanRuntime()

    bootstrap = build_host_agent_bootstrap(
        {},
        fan_runtime_factory=lambda config: runtime,
        fan_history_factory=FakeHistory,
        commissioning_history_factory=FakeHistory,
        thermal_authority_factory=FakeAuthority,
        status_bridge_factory=FakeStatusBridge,
    )

    assert isinstance(
        bootstrap.status_bridge,
        FakeStatusBridge,
    )


def test_bootstrap_builds_host_safety_services():
    runtime = FakeFanRuntime()

    bootstrap = build_host_agent_bootstrap(
        {},
        fan_runtime_factory=lambda config: runtime,
        fan_history_factory=FakeHistory,
        commissioning_history_factory=FakeHistory,
        thermal_authority_factory=FakeAuthority,
        telemetry_factory=FakeTelemetry,
        status_bridge_factory=FakeStatusBridge,
    )

    services = bootstrap.safety_services()

    assert (
        services.fan_telemetry_provider
        == bootstrap.telemetry.snapshot
    )
    assert (
        services.fan_status_publisher
        == bootstrap.publish_fan_status
    )
    assert services.fan_event_recorder is not None
    assert (
        services.thermal_control_handler_factory
        == bootstrap.build_thermal_control_handler
    )


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
