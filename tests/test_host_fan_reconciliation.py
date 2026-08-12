from truepanel.host.reconciliation import (
    HostFanReconciliationCoordinator,
)


class FakeRuntime:
    def __init__(self, *, connected=True):
        self.connected = connected
        self.status_calls = 0

    def status_payload(self):
        self.status_calls += 1
        return {
            "active_profile": "automatic",
        }


class FakeObserver:
    def __init__(self, trace):
        self.trace = trace
        self.telemetry = None
        self.recommendation = object()

    def observe(self, telemetry):
        self.trace.append("observe")
        self.telemetry = telemetry
        return self.recommendation


class FakeSafety:
    def __init__(self, trace, *, decision=None):
        self.trace = trace
        self.decision = decision
        self.snapshot = {
            "telemetry_fresh": True,
        }
        self.post_snapshot = {
            "telemetry_fresh": True,
            "post_transition": True,
        }
        self.reconcile_kwargs = None
        self.status_calls = []
        self.restore_calls = []
        self.telemetry_calls = 0

    def telemetry(self):
        self.telemetry_calls += 1
        self.trace.append("telemetry")
        if self.telemetry_calls > 1:
            return self.post_snapshot
        return self.snapshot

    def reconcile(self, **kwargs):
        self.trace.append("safety")
        self.reconcile_kwargs = kwargs
        return self.decision, self.post_snapshot

    def restore_automatic(self, reason, *, telemetry=None):
        self.restore_calls.append((reason, telemetry))

    def publish_status(self, reason=None):
        self.status_calls.append(reason)


class FakeAuthority:
    def __init__(self, trace):
        self.trace = trace
        self.safety_kwargs = None
        self.reconcile_args = None
        self.reconcile_kwargs = None
        self.result = object()

    def handle_fan_safety_transition(self, **kwargs):
        self.trace.append("thermal_safety")
        self.safety_kwargs = kwargs

    def reconcile(self, recommendation, **kwargs):
        self.trace.append("thermal")
        self.reconcile_args = recommendation
        self.reconcile_kwargs = kwargs
        return self.result


def build_coordinator(
    *,
    connected=True,
    safety_decision=None,
):
    trace = []
    runtime = FakeRuntime(
        connected=connected
    )
    observer = FakeObserver(trace)
    safety = FakeSafety(
        trace,
        decision=safety_decision,
    )
    authority = FakeAuthority(trace)
    fan_events = []
    commissioning_events = []

    coordinator = HostFanReconciliationCoordinator(
        fan_runtime=runtime,
        safety=safety,
        thermal_observer=observer,
        thermal_authority=authority,
        fan_event_source=lambda decision: "safety",
        record_fan_event=lambda *args, **kwargs: (
            fan_events.append((args, kwargs))
        ),
        record_commissioning_event=(
            lambda *args, **kwargs: (
                commissioning_events.append(
                    (args, kwargs)
                )
            )
        ),
    )

    return (
        coordinator,
        trace,
        runtime,
        observer,
        safety,
        authority,
        fan_events,
        commissioning_events,
    )


def test_disconnected_runtime_does_not_reconcile():
    (
        coordinator,
        trace,
        runtime,
        _observer,
        safety,
        _authority,
        _fan_events,
        _commissioning_events,
    ) = build_coordinator(
        connected=False
    )

    assert coordinator.reconcile() is None
    assert trace == []
    assert safety.telemetry_calls == 0
    assert runtime.status_calls == 0


def test_safety_transition_has_first_refusal():
    safety_decision = object()
    (
        coordinator,
        trace,
        _runtime,
        observer,
        safety,
        authority,
        _fan_events,
        _commissioning_events,
    ) = build_coordinator(
        safety_decision=safety_decision
    )

    result = coordinator.reconcile()

    assert result is safety_decision
    assert trace == [
        "telemetry",
        "observe",
        "safety",
        "thermal_safety",
    ]
    assert observer.telemetry is safety.snapshot
    assert authority.reconcile_args is None
    assert (
        authority.safety_kwargs["telemetry"]
        is safety.post_snapshot
    )
    assert (
        authority.safety_kwargs["telemetry_provider"]
        == safety.telemetry
    )
    assert (
        authority.safety_kwargs["restore_automatic"]
        == safety.restore_automatic
    )


def test_clean_safety_cycle_reconciles_thermal_authority():
    (
        coordinator,
        trace,
        runtime,
        observer,
        safety,
        authority,
        fan_events,
        commissioning_events,
    ) = build_coordinator()

    result = coordinator.reconcile()

    assert result is authority.result
    assert trace == [
        "telemetry",
        "observe",
        "safety",
        "thermal",
    ]
    assert (
        authority.reconcile_args
        is observer.recommendation
    )
    assert (
        authority.reconcile_kwargs["telemetry"]
        is safety.snapshot
    )
    assert (
        authority.reconcile_kwargs["runtime_status_provider"]
        == runtime.status_payload
    )
    assert (
        authority.reconcile_kwargs["telemetry_provider"]
        == safety.telemetry
    )
    assert callable(
        authority.reconcile_kwargs["record_fan_event"]
    )
    assert callable(
        authority.reconcile_kwargs[
            "record_commissioning_event"
        ]
    )
    assert fan_events == []
    assert commissioning_events == []


def test_safety_cycle_receives_event_classifier():
    (
        coordinator,
        _trace,
        _runtime,
        _observer,
        safety,
        _authority,
        _fan_events,
        _commissioning_events,
    ) = build_coordinator()

    coordinator.reconcile()

    classifier = safety.reconcile_kwargs[
        "source_classifier"
    ]
    assert classifier(object()) == "safety"
