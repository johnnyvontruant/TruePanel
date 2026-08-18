from dataclasses import dataclass

from truepanel.hardware.fan_control import FanProfile
from truepanel.holodeck.invariants import (
    DEFAULT_INVARIANT_RULES,
    InvariantRule,
    evaluate_observation,
    evaluate_timeline,
)


@dataclass(frozen=True)
class Recommendation:
    recommended_profile: FanProfile


def observation(*, state=None, profile=FanProfile.AUTOMATIC, storage="NOMINAL"):
    return {
        "state": {
            "simulation": True,
            "read_only": True,
            "telemetry_fresh": True,
            "fans": {"fan_channels": []},
            "pools": [],
            **(state or {}),
        },
        "recommendation": Recommendation(profile),
        "snapshot": {
            "health": {"subsystems": {"storage": {"state": storage}}}
        },
    }


def test_nominal_observation_passes_all_flight_rules():
    result = evaluate_observation(observation())

    assert result.passed is True
    assert result.observation_count == 1
    assert result.rule_count == len(DEFAULT_INVARIANT_RULES)
    assert result.violations == ()


def test_hardware_isolation_rule_fails_closed_on_missing_flags():
    result = evaluate_observation({"state": {}})

    violation = result.violations_for("holodeck.hardware_isolated")[0]
    assert violation.observation_index == 0
    assert violation.evidence == (("read_only", "null"), ("simulation", "null"))


def test_stale_telemetry_requires_automatic():
    bad = observation(
        state={"telemetry_fresh": False},
        profile=FanProfile.AFTERBURNERS,
    )
    result = evaluate_observation(bad)

    violation = result.violations_for("thermal.stale_is_automatic")[0]
    assert violation.evidence == (
        ("recommended_profile", "afterburners"),
        ("telemetry_fresh", "false"),
    )
    assert evaluate_observation(
        observation(state={"telemetry_fresh": False})
    ).violations_for("thermal.stale_is_automatic") == ()


def test_stalled_fan_cannot_claim_healthy_or_clear_alarm():
    state = {
        "fans": {
            "fan_channels": [
                {"number": 2, "rpm": 0, "stalled": True, "healthy": True, "alarm": False}
            ]
        }
    }
    violation = evaluate_observation(observation(state=state)).violations_for(
        "cooling.stalled_not_healthy"
    )[0]

    assert violation.evidence == (
        ("healthy", "true"),
        ("stalled_channels", "2"),
    )


def test_degraded_pool_cannot_be_reported_nominal():
    bad = observation(
        state={"pools": [{"name": "HDDs", "health": "DEGRADED"}]},
        storage="NOMINAL",
    )
    violation = evaluate_observation(bad).violations_for(
        "storage.degraded_not_nominal"
    )[0]

    assert violation.evidence == (
        ("degraded_pools", "HDDs"),
        ("storage_state", "NOMINAL"),
    )
    assert evaluate_observation(
        observation(
            state={"pools": [{"name": "HDDs", "health": "DEGRADED"}]},
            storage="DEGRADED",
        )
    ).passed


def test_timeline_order_and_evidence_are_deterministic():
    custom = InvariantRule(
        "test.always",
        "Always fails",
        lambda item: (("value", str(item)),),
    )

    first = evaluate_timeline(("b", "a"), (custom,))
    second = evaluate_timeline(("b", "a"), (custom,))

    assert first == second
    assert [item.observation_index for item in first.violations] == [0, 1]
    assert [item.evidence for item in first.violations] == [
        (("value", "b"),),
        (("value", "a"),),
    ]


def test_rule_validation_and_iterables_are_materialized_once():
    result = evaluate_timeline(
        (observation() for _ in range(2)),
        (rule for rule in DEFAULT_INVARIANT_RULES),
    )

    assert result.passed
    assert result.observation_count == 2
