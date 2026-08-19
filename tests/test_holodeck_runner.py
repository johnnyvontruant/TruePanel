from pathlib import Path

import pytest

from truepanel.hardware.fan_control import FanProfile
from truepanel.holodeck import DeterministicClock, HoloDeckHostProvider
from truepanel.holodeck.runner import HoloDeckScenarioRunner

FIXTURE = Path(__file__).parent / "fixtures" / "hosts" / "battlestation" / "host.json"


def build_runner(tmp_path):
    provider = HoloDeckHostProvider.from_path(
        FIXTURE,
        clock=DeterministicClock(0),
    )
    return provider, HoloDeckScenarioRunner(provider, runtime_dir=tmp_path)


def test_fan_stall_while_temperature_rises(tmp_path):
    provider, runner = build_runner(tmp_path)
    runner.step()

    provider.inject("temperature", sensor="cpu", value=78)
    provider.inject("fan_stall", channel=1)
    first = runner.step()
    second = runner.step(1)
    third = runner.step(1)

    assert first.recommendation.recommended_profile is FanProfile.AFTERBURNERS
    assert first.recommendation.telemetry_valid is True
    assert first.events == ()
    assert second.events == ()
    assert [event.event_id for event in third.events] == [
        "thermal.fan1.low_rpm"
    ]
    assert third.snapshot["health"]["subsystems"]["cooling"]["state"] == "DEGRADED"


def test_disk_fault_emits_storage_incident(tmp_path):
    provider, runner = build_runner(tmp_path)
    runner.step()

    provider.inject("disk_fault", bay=4)
    observation = runner.step(1)

    assert [event.event_id for event in observation.events] == [
        "storage.disk4.health_degraded"
    ]
    event = observation.events[0]
    assert event.metadata["physical_bay"] == 4
    assert event.metadata["old_state"] == "healthy"
    assert event.metadata["new_state"] == "critical"


def test_primary_network_down_degrades_mission_control(tmp_path):
    provider, runner = build_runner(tmp_path)
    baseline = runner.step()
    assert baseline.snapshot["health"]["subsystems"]["network"]["state"] == "NOMINAL"

    provider.inject("network_down", interface="enp116s0")
    observation = runner.step(1)

    network = observation.snapshot["health"]["subsystems"]["network"]
    assert network["state"] == "DEGRADED"
    assert network["summary"] == "Primary network link down"


def test_lcd_disconnect_degrades_front_panel(tmp_path):
    provider, runner = build_runner(tmp_path)
    baseline = runner.step()
    assert baseline.snapshot["health"]["subsystems"]["front_panel"]["state"] == "NOMINAL"

    provider.inject("lcd_disconnect")
    observation = runner.step(1)

    assert observation.snapshot["lcd"]["reader"]["connected"] is False
    front_panel = observation.snapshot["health"]["subsystems"]["front_panel"]
    assert front_panel["state"] == "DEGRADED"
    assert front_panel["summary"] == "Front panel degraded"


def test_stale_telemetry_recommends_fail_safe_automatic(tmp_path):
    provider, runner = build_runner(tmp_path)
    provider.inject("temperature", sensor="cpu", value=78)
    hot = runner.step()
    assert hot.recommendation.recommended_profile is FanProfile.AFTERBURNERS

    provider.inject("telemetry_stale")
    stale = runner.step(1)

    assert stale.recommendation.recommended_profile is FanProfile.AUTOMATIC
    assert stale.recommendation.telemetry_valid is False
    assert stale.recommendation.changed is True
    assert "stale" in stale.recommendation.reason.lower()


def test_runner_uses_only_isolated_runtime_paths(tmp_path):
    provider, runner = build_runner(tmp_path)
    runner.step()

    bridges = (
        runner.snapshot_service.fan_control_bridge,
        runner.snapshot_service.lcd_reader_bridge,
        runner.snapshot_service.lcd_display_bridge,
    )
    assert all(str(bridge.path).startswith(str(tmp_path)) for bridge in bridges)
    assert runner.snapshot_service.history_path.parent == tmp_path


@pytest.mark.parametrize(
    "runtime_dir",
    (
        "/",
        "/dev/truepanel-holodeck",
        "/etc/truepanel-holodeck",
        "/proc/truepanel-holodeck",
        "/run/truepanel-holodeck",
        "/sys/truepanel-holodeck",
        "/var/lib/truepanel-holodeck",
    ),
)
def test_runner_rejects_protected_production_runtime_paths(runtime_dir):
    twin = HoloDeckHostProvider.from_path(
        FIXTURE,
        clock=DeterministicClock(0),
    )

    with pytest.raises(ValueError, match="protected production path"):
        HoloDeckScenarioRunner(twin, runtime_dir=runtime_dir)


def test_runner_rejects_symlink_alias_to_protected_runtime(tmp_path):
    alias = tmp_path / "runtime-alias"
    alias.symlink_to("/var/lib")
    twin = HoloDeckHostProvider.from_path(FIXTURE)

    with pytest.raises(ValueError, match="protected production path"):
        HoloDeckScenarioRunner(twin, runtime_dir=alias / "truepanel")


def test_runner_rejects_duck_typed_simulation_provider(tmp_path):
    class FakeProvider:
        simulation = True

    with pytest.raises(ValueError, match="requires a simulation provider"):
        HoloDeckScenarioRunner(FakeProvider(), runtime_dir=tmp_path)
