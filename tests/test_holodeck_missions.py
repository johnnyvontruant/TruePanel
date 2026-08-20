import pytest

from truepanel.holodeck.catalog import host_fixture
from truepanel.holodeck.missions import mission_names, mission_scenario
from truepanel.holodeck.provider import HoloDeckHostProvider, SimulationSafetyError


EXPECTED_MISSIONS = (
    "thermal-ramp",
    "fan-stall-recovery",
    "drive-failure",
    "drive-failure-recovery",
    "drive-removal",
    "drive-removal-reinsert",
    "network-flap",
    "lcd-loss-recovery",
    "stale-telemetry-recovery",
)


def provider_for(name):
    scenario = mission_scenario(name)
    return HoloDeckHostProvider(host_fixture(scenario.host), scenario=scenario)


def advance_to_end(provider):
    scenario_end = max((event.at for event in provider._events), default=0)
    return provider.advance(scenario_end)


def test_mission_catalog_has_stable_names():
    assert mission_names() == EXPECTED_MISSIONS


@pytest.mark.parametrize("name", EXPECTED_MISSIONS)
def test_missions_are_deterministic(name):
    first = provider_for(name)
    second = provider_for(name)
    first_state = advance_to_end(first)
    second_state = advance_to_end(second)
    assert first_state == second_state
    assert first.applied_events == second.applied_events
    assert [event.type for event in first.applied_events] == [event.type for event in mission_scenario(name).events]


@pytest.mark.parametrize("name", EXPECTED_MISSIONS)
def test_missions_remain_hardware_isolated(name):
    provider = provider_for(name)
    with pytest.raises(SimulationSafetyError):
        provider.hardware.open("/dev/ttyS1")
    with pytest.raises(SimulationSafetyError):
        provider.hardware.run("zpool", "status")


def test_thermal_ramp_heats_and_recovers():
    provider = provider_for("thermal-ramp")
    assert provider.update()["cpu_temperature_c"] == 51.0
    assert provider.advance(180)["cpu_temperature_c"] == 74.0
    assert provider.advance(120)["cpu_temperature_c"] == 54.0


def test_fan_stall_recovery_restores_baseline_rpm():
    provider = provider_for("fan-stall-recovery")
    stalled = provider.advance(30)["fans"]["fan_channels"][0]
    assert stalled["rpm"] == 0
    assert stalled["alarm"] is True
    recovered = provider.advance(90)["fans"]["fan_channels"][0]
    assert recovered["rpm"] == 1510
    assert recovered["alarm"] is False


def test_drive_failure_degrades_pool():
    state = provider_for("drive-failure").advance(35)
    assert state["enclosure"]["bays"][2]["health"] == "FAULTED"
    assert next(pool for pool in state["pools"] if pool["name"] == "HDDs")["health"] == "DEGRADED"


def test_drive_failure_recovery_returns_drive_and_pool_online():
    provider = provider_for("drive-failure-recovery")
    degraded = provider.advance(35)
    assert degraded["enclosure"]["bays"][2]["health"] == "FAULTED"
    assert next(pool for pool in degraded["pools"] if pool["name"] == "HDDs")["health"] == "DEGRADED"
    drive_recovered = provider.advance(85)
    assert drive_recovered["enclosure"]["bays"][2]["health"] == "ONLINE"
    assert next(pool for pool in drive_recovered["pools"] if pool["name"] == "HDDs")["health"] == "DEGRADED"
    recovered = provider.advance(5)
    assert next(pool for pool in recovered["pools"] if pool["name"] == "HDDs")["health"] == "ONLINE"


def test_drive_removal_marks_bay_absent_and_degrades_pool():
    state = provider_for("drive-removal").advance(35)
    bay = state["enclosure"]["bays"][2]
    assert bay["present"] is False
    assert bay["device"] is None
    assert next(pool for pool in state["pools"] if pool["name"] == "HDDs")["health"] == "DEGRADED"


def test_drive_reinsert_restores_identity_before_pool_recovers():
    provider = provider_for("drive-removal-reinsert")
    degraded = provider.advance(35)
    assert degraded["enclosure"]["bays"][2]["present"] is False
    inserted = provider.advance(85)
    bay = inserted["enclosure"]["bays"][2]
    assert bay["present"] is True
    assert bay["device"] is not None
    assert bay["health"] == "ONLINE"
    assert next(pool for pool in inserted["pools"] if pool["name"] == "HDDs")["health"] == "DEGRADED"
    recovered = provider.advance(5)
    assert next(pool for pool in recovered["pools"] if pool["name"] == "HDDs")["health"] == "ONLINE"


def test_network_flap_recovers_primary_link():
    provider = provider_for("network-flap")
    assert provider.advance(30)["network"]["enp116s0"]["link_up"] is False
    recovered = provider.advance(60)["network"]["enp116s0"]
    assert recovered["link_up"] is True
    assert recovered["operstate"] == "UP"


def test_lcd_loss_recovers():
    provider = provider_for("lcd-loss-recovery")
    assert provider.advance(30)["lcd"]["connected"] is False
    assert provider.advance(60)["lcd"]["connected"] is True


def test_stale_telemetry_recovers():
    provider = provider_for("stale-telemetry-recovery")
    assert provider.advance(30)["telemetry_fresh"] is False
    assert provider.advance(90)["telemetry_fresh"] is True


def test_unknown_mission_reports_available_names():
    with pytest.raises(ValueError, match="thermal-ramp"):
        mission_scenario("warp-core-breach")
