import inspect

from truepanel.host import factory
from truepanel.host.hooks import HostAgentSafetyServices


class FakeFanRuntime:
    def __init__(
        self,
        *,
        enabled=True,
    ):
        self.enabled = enabled

    def shutdown(self):
        pass


def telemetry():
    return {
        "fan_status": {},
        "temperatures_c": (),
        "telemetry_fresh": True,
    }


def test_disabled_fan_runtime_builds_no_server():
    runtime = FakeFanRuntime(
        enabled=False
    )

    server = (
        factory.build_fan_command_server(
            fan_runtime=runtime,
            telemetry_provider=telemetry,
        )
    )

    assert server is None


def test_enabled_fan_runtime_builds_processor_and_server():
    runtime = FakeFanRuntime()

    server = (
        factory.build_fan_command_server(
            fan_runtime=runtime,
            telemetry_provider=telemetry,
        )
    )

    assert server is not None
    assert server.processor.runtime is runtime

    assert (
        server.processor.telemetry_provider
        is telemetry
    )


def test_fan_callbacks_reach_processor():
    runtime = FakeFanRuntime()

    def publish():
        pass

    def record(
        decision,
        telemetry_payload,
        source,
    ):
        del decision
        del telemetry_payload
        del source

    def thermal(action):
        return {
            "action": action
        }

    server = (
        factory.build_fan_command_server(
            fan_runtime=runtime,
            telemetry_provider=telemetry,
            status_publisher=publish,
            event_recorder=record,
            thermal_control_handler=thermal,
        )
    )

    processor = server.processor

    assert (
        processor.status_publisher
        is publish
    )
    assert (
        processor.event_recorder
        is record
    )
    assert (
        processor.thermal_control_handler
        is thermal
    )


def test_host_runtime_receives_only_fan_command_factory(
    monkeypatch,
):
    fan_runtime = FakeFanRuntime()
    fan_server = object()
    captured_fan = {}

    def build_fan(**kwargs):
        captured_fan.update(kwargs)
        return fan_server

    monkeypatch.setattr(
        factory,
        "build_fan_command_server",
        build_fan,
    )

    runtime = (
        factory.build_host_agent_runtime(
            fan_runtime=fan_runtime,
            safety_services=HostAgentSafetyServices(
                fan_telemetry_provider=telemetry,
            ),
        )
    )

    assert runtime.fan_server is None
    assert not hasattr(runtime, "lcd_server")
    assert not hasattr(runtime, "_lcd_server_factory")

    built_fan = (
        runtime._fan_server_factory()
    )

    assert built_fan is fan_server

    assert (
        captured_fan["fan_runtime"]
        is fan_runtime
    )

    assert (
        captured_fan[
            "telemetry_provider"
        ]()
        == telemetry()
    )

    assert (
        runtime.safety.telemetry()
        == telemetry()
    )


def test_host_factory_has_no_application_hook_boundary():
    runtime_parameters = inspect.signature(
        factory.build_host_agent_runtime
    ).parameters
    bootstrap_parameters = inspect.signature(
        factory.build_host_agent_runtime_from_bootstrap
    ).parameters

    assert "application_hooks" not in runtime_parameters
    assert "application_hooks" not in bootstrap_parameters


def test_factory_does_not_start_runtime(
    monkeypatch,
):
    called = []

    monkeypatch.setattr(
        factory.HostAgentRuntime,
        "start",
        lambda self: called.append(
            "start"
        ),
    )

    runtime = (
        factory.build_host_agent_runtime(
            fan_runtime=FakeFanRuntime(),
            safety_services=HostAgentSafetyServices(
                fan_telemetry_provider=telemetry
            ),
        )
    )

    assert runtime.started is False
    assert called == []


def test_factory_accepts_socketless_server_factory():
    runtime = factory.build_host_agent_runtime(
        fan_runtime=FakeFanRuntime(),
        safety_services=HostAgentSafetyServices(
            fan_telemetry_provider=telemetry,
        ),
        fan_server_factory=lambda: None,
    )

    runtime.start()

    assert runtime.started is True
    assert runtime.fan_server is None


class FakeBootstrap:
    def __init__(self, fan_runtime, safety_services):
        self.fan_runtime = fan_runtime
        self._safety_services = safety_services
        self.safety_service_calls = 0

    def safety_services(self):
        self.safety_service_calls += 1
        return self._safety_services


def test_bootstrap_factory_unwraps_privileged_dependencies():
    fan_runtime = FakeFanRuntime()
    services = HostAgentSafetyServices(
        fan_telemetry_provider=telemetry,
    )
    bootstrap = FakeBootstrap(
        fan_runtime,
        services,
    )

    runtime = (
        factory.build_host_agent_runtime_from_bootstrap(
            bootstrap=bootstrap,
        )
    )

    assert runtime._fan_runtime is fan_runtime
    assert runtime.safety.telemetry() == telemetry()
    assert bootstrap.safety_service_calls == 1
    assert runtime.started is False
