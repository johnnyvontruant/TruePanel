from pathlib import Path

import pytest

from truepanel.hardware.fan_control import FanProfile
from truepanel.holodeck.host_agent import (
    HoloDeckFanTelemetryProvider,
    build_holodeck_host_agent_runtime,
)
from truepanel.holodeck.provider import HoloDeckHostProvider
from truepanel.host.runtime import HostAgentRuntime

FIXTURE = (
    Path(__file__).parent
    / "fixtures/hosts/battlestation/host.json"
)


def provider():
    return HoloDeckHostProvider.from_path(FIXTURE)


def test_runtime_starts_without_socket_and_holds_simulated_ownership():
    runtime = build_holodeck_host_agent_runtime(provider())

    assert isinstance(runtime, HostAgentRuntime)
    runtime.start()

    assert runtime.started is True
    assert runtime.fan_server is None
    assert runtime.holodeck_ownership.acquired is True


def test_baseline_cycle_uses_real_host_runtime_contract():
    runtime = build_holodeck_host_agent_runtime(provider())
    runtime.start()

    result = runtime.service_cycle(publish_reason="holodeck")

    assert result["reconciliation"] is None
    assert result["recommendation"].recommended_profile is (
        FanProfile.COOLING_BOOST
    )
    assert result["status"]["last_reason"] == "holodeck"
    assert runtime.read_fan_status()["connected"] is True


def test_thermal_runaway_engages_real_safety_service_in_memory():
    twin = provider()
    runtime = build_holodeck_host_agent_runtime(twin)
    runtime.start()
    twin.inject("temperature", sensor="cpu", value=92)

    result = runtime.service_cycle()

    decision = result["reconciliation"]
    assert decision.effective_profile is FanProfile.AFTERBURNERS
    assert decision.pwm == 255
    assert runtime.holodeck_executor.decisions == [decision]
    assert runtime.safety.fan_runtime.status_payload()[
        "active_profile"
    ] == "afterburners"
    state = twin.update()
    assert state["fans"]["active_profile"] == "afterburners"
    assert [
        fan["pwm"]
        for fan in state["fans"]["fan_channels"][:2]
    ] == [255, 255]


def test_explicit_stale_event_overrides_present_temperatures():
    twin = provider()
    telemetry = HoloDeckFanTelemetryProvider(twin)
    twin.inject("telemetry_stale")

    snapshot = telemetry.snapshot()
    assert snapshot["temperatures_c"]
    assert snapshot["telemetry_fresh"] is False

    runtime = build_holodeck_host_agent_runtime(twin)
    recommendation = runtime.service_cycle(reconcile=False)[
        "recommendation"
    ]
    assert recommendation.telemetry_valid is False
    assert recommendation.recommended_profile is FanProfile.AUTOMATIC
    assert runtime.holodeck_executor.decisions == []


def test_shutdown_closes_only_simulated_executor_and_releases_lease():
    runtime = build_holodeck_host_agent_runtime(provider())
    runtime.start()
    runtime.shutdown()
    runtime.shutdown()

    assert runtime.started is False
    assert runtime.holodeck_executor.closed is True
    assert runtime.holodeck_ownership.acquired is False


def test_holodeck_hardware_boundary_remains_deny_all():
    twin = provider()
    runtime = build_holodeck_host_agent_runtime(twin)
    runtime.start()
    runtime.service_cycle()

    with pytest.raises(RuntimeError, match="hardware writes"):
        twin.hardware.write("pwm1", 255)
