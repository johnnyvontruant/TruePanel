from pathlib import Path
from types import SimpleNamespace

import pytest

from truepanel.hardware.fan_control import FanProfile
from truepanel.hardware.thermal_fan_policy import (
    ThermalFanRecommendation,
)
from truepanel.host.thermal_observer import HostThermalObserver


class FakePolicy:
    def __init__(self, recommendations):
        self.recommendations = list(recommendations)
        self.calls = []

    def evaluate(self, temperatures, *, telemetry_fresh=True):
        self.calls.append((tuple(temperatures), telemetry_fresh))
        return self.recommendations.pop(0)


class FakeHistory:
    def __init__(self):
        self.events = []

    def append(self, event):
        self.events.append(dict(event))
        return True


def recommendation(
    profile=FanProfile.BALANCED,
    *,
    valid=True,
    changed=True,
    temperature=47.0,
):
    return ThermalFanRecommendation(
        recommended_profile=profile,
        hottest_temperature_c=temperature,
        telemetry_valid=valid,
        changed=changed,
        reason="Host observer recommendation.",
    )


def make_observer(policy, history, authority, **kwargs):
    return HostThermalObserver(
        policy=policy,
        policy_mode=kwargs.pop("policy_mode", "observe_only"),
        thermal_authority=authority,
        history=history,
        runtime_status_provider=lambda: {
            "active_profile": "automatic",
            "control_authority": "automatic",
        },
        **kwargs,
    )


def test_observer_publishes_recommendation_to_authority():
    result = recommendation()
    authority = SimpleNamespace(current_recommendation=None)
    history = FakeHistory()
    observer = make_observer(
        FakePolicy([result]),
        history,
        authority,
    )

    observed = observer.observe(
        {
            "temperatures_c": (47.0,),
            "telemetry_fresh": True,
        }
    )

    assert observed is result
    assert authority.current_recommendation is result
    assert history.events[0]["recommended_profile"] == "balanced"
    assert history.events[0]["previous_recommended_profile"] == "automatic"


def test_observer_records_only_signature_changes():
    authority = SimpleNamespace(current_recommendation=None)
    history = FakeHistory()
    policy = FakePolicy(
        [
            recommendation(FanProfile.BALANCED),
            recommendation(FanProfile.BALANCED),
            recommendation(FanProfile.COOLING_BOOST, temperature=52.0),
        ]
    )
    observer = make_observer(policy, history, authority)
    telemetry = {
        "temperatures_c": (47.0,),
        "telemetry_fresh": True,
    }

    observer.observe(telemetry)
    observer.observe(telemetry)
    observer.observe(telemetry)

    assert len(history.events) == 2
    assert history.events[1]["recommended_profile"] == "cooling_boost"
    assert history.events[1]["previous_recommended_profile"] == "balanced"


def test_observer_records_telemetry_validity_transition():
    authority = SimpleNamespace(current_recommendation=None)
    history = FakeHistory()
    policy = FakePolicy(
        [
            recommendation(FanProfile.BALANCED, valid=True),
            recommendation(FanProfile.BALANCED, valid=False),
        ]
    )
    observer = make_observer(policy, history, authority)

    observer.observe({"temperatures_c": (47.0,), "telemetry_fresh": True})
    observer.observe({"temperatures_c": (), "telemetry_fresh": False})

    assert len(history.events) == 2
    assert history.events[-1]["telemetry_valid"] is False


def test_disabled_mode_forces_unavailable_telemetry_evaluation():
    authority = SimpleNamespace(current_recommendation=None)
    history = FakeHistory()
    policy = FakePolicy(
        [recommendation(FanProfile.AUTOMATIC, valid=False, temperature=None)]
    )
    observer = make_observer(
        policy,
        history,
        authority,
        policy_mode="disabled",
    )

    observer.observe(
        {
            "temperatures_c": (99.0,),
            "telemetry_fresh": True,
        }
    )

    assert policy.calls == [((), False)]


def test_observer_can_pull_host_telemetry():
    authority = SimpleNamespace(current_recommendation=None)
    history = FakeHistory()
    policy = FakePolicy([recommendation()])
    calls = []

    def telemetry_provider():
        calls.append(True)
        return {
            "temperatures_c": (48.0,),
            "telemetry_fresh": True,
        }

    observer = make_observer(
        policy,
        history,
        authority,
        telemetry_provider=telemetry_provider,
    )

    observer.observe()

    assert calls == [True]
    assert policy.calls == [((48.0,), True)]


def test_observer_requires_telemetry_without_provider():
    observer = make_observer(
        FakePolicy([]),
        FakeHistory(),
        SimpleNamespace(current_recommendation=None),
    )

    with pytest.raises(RuntimeError, match="requires telemetry"):
        observer.observe()


def test_host_observer_has_no_actuator_path():
    source = Path("truepanel/host/thermal_observer.py").read_text(
        encoding="utf-8"
    )

    for forbidden in (
        "request_profile(",
        "fan_command_client",
        "set_manual_pwm",
        "FanHardwareExecutor",
        "fan_control_runtime.request",
        "write_int",
        "/sys/",
    ):
        assert forbidden not in source
