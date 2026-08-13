import pytest

from truepanel.host.runtime import HostAgentRuntime


class FakeGuard:
    def __init__(self, events):
        self.events = events

    def acquire(self):
        self.events.append("ownership.acquire")

    def release(self):
        self.events.append("ownership.release")


class FakeFanRuntime:
    def __init__(self, events):
        self.events = events

    def shutdown(self):
        self.events.append("fan_runtime.shutdown")


class FakeSafety:
    def __init__(self, events):
        self.events = events

    def publish_status(self, reason=None):
        self.events.append(("publish", reason))
        return {"reason": reason}


class FakeReconciliation:
    def __init__(self, events, *, fail=False):
        self.events = events
        self.fail = fail

    def reconcile(self):
        self.events.append("reconcile")
        if self.fail:
            raise RuntimeError("reconciliation boom")
        return "decision"

    def observe(self, telemetry=None):
        self.events.append(("observe", telemetry))
        return "recommendation"


class FakeLifecycle:
    def __init__(self, events):
        self.events = events

    def end_supervised_session(self, *args, **kwargs):
        self.events.append("end_supervised")
        return "supervised-ended"

    def end_bounded_automatic_lease(self, *args, **kwargs):
        self.events.append("end_bounded")
        return "bounded-ended"

    def supervised_session_active(self):
        return False


def build_runtime(events, *, fail_reconcile=False):
    return HostAgentRuntime(
        fan_runtime=FakeFanRuntime(events),
        safety=FakeSafety(events),
        ownership_guard=FakeGuard(events),
        fan_reconciliation=FakeReconciliation(
            events,
            fail=fail_reconcile,
        ),
        thermal_lifecycle=FakeLifecycle(events),
        fan_server_factory=lambda: None,
        lcd_server_factory=lambda: None,
    )


def test_prestart_service_cycle_allows_read_only_priming():
    events = []
    runtime = build_runtime(events)

    result = runtime.service_cycle(
        reconcile=False,
        publish_reason="prime",
    )

    assert events == [
        ("observe", None),
        ("publish", "prime"),
    ]
    assert result == {
        "reconciliation": None,
        "recommendation": "recommendation",
        "status": {"reason": "prime"},
    }


def test_prestart_active_cycle_refuses_without_ownership():
    events = []
    runtime = build_runtime(events)

    with pytest.raises(
        RuntimeError,
        match="does not own Host hardware",
    ):
        runtime.service_cycle()

    assert events == []


def test_owned_service_cycle_preserves_reconcile_observe_publish_order():
    events = []
    runtime = build_runtime(events)
    runtime.start()
    events.clear()

    result = runtime.service_cycle()

    assert events == [
        "reconcile",
        ("observe", None),
        ("publish", None),
    ]
    assert result["reconciliation"] == "decision"
    assert result["recommendation"] == "recommendation"


def test_reconciliation_failure_still_observes_and_publishes():
    events = []
    runtime = build_runtime(
        events,
        fail_reconcile=True,
    )
    runtime.start()
    events.clear()

    result = runtime.service_cycle()

    assert events == [
        "reconcile",
        ("observe", None),
        ("publish", None),
    ]
    assert result["reconciliation"] is None
    assert result["recommendation"] == "recommendation"


def test_actuating_lifecycle_refuses_before_ownership():
    events = []
    runtime = build_runtime(events)

    with pytest.raises(
        RuntimeError,
        match="does not own Host hardware",
    ):
        runtime.end_supervised_thermal_session(
            "test",
            lifecycle_action="stop",
        )

    with pytest.raises(
        RuntimeError,
        match="does not own Host hardware",
    ):
        runtime.end_bounded_automatic_lease(
            "test",
            lifecycle_action="stop",
        )

    assert events == []


def test_owned_lifecycle_remains_available():
    events = []
    runtime = build_runtime(events)
    runtime.start()
    events.clear()

    assert runtime.end_supervised_thermal_session(
        "test",
        lifecycle_action="stop",
    ) == "supervised-ended"
    assert runtime.end_bounded_automatic_lease(
        "test",
        lifecycle_action="stop",
    ) == "bounded-ended"

    assert events == [
        "end_supervised",
        "end_bounded",
    ]
