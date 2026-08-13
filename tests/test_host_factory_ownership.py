from truepanel.host.factory import (
    build_host_agent_runtime_from_bootstrap,
)
from truepanel.host.hooks import HostAgentSafetyServices


class FakeFanRuntime:
    enabled = False

    def shutdown(self):
        pass


class FakeBootstrap:
    def __init__(self):
        self.fan_runtime = FakeFanRuntime()

    def safety_services(self):
        return HostAgentSafetyServices(
            fan_telemetry_provider=lambda: {},
        )


def test_bootstrap_factory_defaults_to_embedded_owner(tmp_path):
    runtime = build_host_agent_runtime_from_bootstrap(
        bootstrap=FakeBootstrap(),
        ownership_path=tmp_path / "host-owner.lock",
    )

    assert runtime._ownership_guard.owner_name == "embedded-lcd"


def test_bootstrap_factory_accepts_standalone_owner(tmp_path):
    runtime = build_host_agent_runtime_from_bootstrap(
        bootstrap=FakeBootstrap(),
        owner_name="standalone-host-agent",
        ownership_path=tmp_path / "host-owner.lock",
    )

    assert (
        runtime._ownership_guard.owner_name
        == "standalone-host-agent"
    )
