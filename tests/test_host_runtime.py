import pytest

from truepanel.host.runtime import HostAgentRuntime


class FakeServer:
    def __init__(
        self,
        name,
        events,
        *,
        fail_start=False,
        fail_stop=False,
    ):
        self.name = name
        self.events = events
        self.fail_start = fail_start
        self.fail_stop = fail_stop
        self.start_calls = 0
        self.stop_calls = 0

    def start(self):
        self.start_calls += 1
        self.events.append(
            f"{self.name}.start"
        )

        if self.fail_start:
            raise RuntimeError(
                f"{self.name} start failure"
            )

    def stop(self):
        self.stop_calls += 1
        self.events.append(
            f"{self.name}.stop"
        )

        if self.fail_stop:
            raise RuntimeError(
                f"{self.name} stop failure"
            )


class FakeFanRuntime:
    def __init__(
        self,
        events,
        *,
        fail_shutdown=False,
    ):
        self.events = events
        self.fail_shutdown = fail_shutdown
        self.shutdown_calls = 0

    def shutdown(self):
        self.shutdown_calls += 1
        self.events.append(
            "fan_runtime.shutdown"
        )

        if self.fail_shutdown:
            raise RuntimeError(
                "fan runtime shutdown failure"
            )


def build_runtime(
    events,
    *,
    fan_server=None,
    fan_runtime=None,
    safety=None,
    **kwargs,
):
    return HostAgentRuntime(
        fan_runtime=(
            fan_runtime
            if fan_runtime is not None
            else FakeFanRuntime(events)
        ),
        safety=(
            safety
            if safety is not None
            else object()
        ),
        fan_server_factory=lambda: fan_server,
        **kwargs,
    )


def test_runtime_starts_fan_server_only():
    events = []
    fan_server = FakeServer(
        "fan_server",
        events,
    )
    runtime = build_runtime(
        events,
        fan_server=fan_server,
    )

    runtime.start()

    assert events == [
        "fan_server.start",
    ]
    assert runtime.started is True
    assert runtime.fan_server is fan_server
    assert not hasattr(runtime, "lcd_server")
    assert not hasattr(runtime, "_lcd_server_factory")


def test_runtime_allows_missing_fan_server():
    events = []
    runtime = build_runtime(events)

    runtime.start()

    assert runtime.started is True
    assert runtime.fan_server is None
    assert events == []


def test_runtime_start_is_idempotent():
    events = []
    fan_server = FakeServer(
        "fan_server",
        events,
    )
    runtime = build_runtime(
        events,
        fan_server=fan_server,
    )

    runtime.start()
    runtime.start()

    assert fan_server.start_calls == 1


def test_shutdown_stops_fan_then_runtime():
    events = []
    fan_runtime = FakeFanRuntime(events)
    fan_server = FakeServer(
        "fan_server",
        events,
    )
    runtime = build_runtime(
        events,
        fan_server=fan_server,
        fan_runtime=fan_runtime,
    )

    runtime.start()
    events.clear()
    runtime.shutdown()

    assert events == [
        "fan_server.stop",
        "fan_runtime.shutdown",
    ]
    assert runtime.started is False
    assert runtime.fan_server is None


def test_shutdown_is_idempotent():
    events = []
    fan_runtime = FakeFanRuntime(events)
    fan_server = FakeServer(
        "fan_server",
        events,
    )
    runtime = build_runtime(
        events,
        fan_server=fan_server,
        fan_runtime=fan_runtime,
    )

    runtime.start()
    runtime.shutdown()
    runtime.shutdown()

    assert fan_server.stop_calls == 1
    assert fan_runtime.shutdown_calls == 1


def test_fan_start_failure_restores_runtime():
    events = []
    fan_runtime = FakeFanRuntime(events)
    fan_server = FakeServer(
        "fan_server",
        events,
        fail_start=True,
    )
    runtime = build_runtime(
        events,
        fan_server=fan_server,
        fan_runtime=fan_runtime,
    )

    with pytest.raises(
        RuntimeError,
        match="fan_server start failure",
    ):
        runtime.start()

    assert events == [
        "fan_server.start",
        "fan_server.stop",
        "fan_runtime.shutdown",
    ]
    assert runtime.started is False


def test_shutdown_continues_after_server_failure():
    events = []
    fan_runtime = FakeFanRuntime(events)
    fan_server = FakeServer(
        "fan_server",
        events,
        fail_stop=True,
    )
    runtime = build_runtime(
        events,
        fan_server=fan_server,
        fan_runtime=fan_runtime,
    )

    runtime.start()
    events.clear()
    runtime.shutdown()

    assert events == [
        "fan_server.stop",
        "fan_runtime.shutdown",
    ]
    assert fan_runtime.shutdown_calls == 1


def test_shutdown_tolerates_fan_runtime_failure():
    events = []
    fan_runtime = FakeFanRuntime(
        events,
        fail_shutdown=True,
    )
    runtime = build_runtime(
        events,
        fan_runtime=fan_runtime,
    )

    runtime.start()
    runtime.shutdown()

    assert events == [
        "fan_runtime.shutdown",
    ]
    assert runtime.started is False


def test_runtime_cannot_restart_after_shutdown():
    events = []
    runtime = build_runtime(events)

    runtime.start()
    runtime.shutdown()

    with pytest.raises(
        RuntimeError,
        match="cannot restart after shutdown",
    ):
        runtime.start()


def test_runtime_owns_safety_coordinator():
    events = []
    safety = object()
    runtime = build_runtime(
        events,
        safety=safety,
    )

    assert runtime.safety is safety


class FakeSafetySurface:
    def __init__(self):
        self.telemetry_calls = 0
        self.status_reasons = []

    def telemetry(self):
        self.telemetry_calls += 1
        return {"telemetry_fresh": True}

    def publish_status(self, reason=None):
        self.status_reasons.append(reason)
        return {"reason": reason}


class FakeReconciliationSurface:
    def __init__(self):
        self.observe_calls = []

    def observe(self, telemetry=None):
        self.observe_calls.append(telemetry)
        return {"recommended_profile": "automatic"}

    def reconcile(self):
        return "reconciled"


def test_runtime_exposes_host_telemetry_and_status():
    events = []
    safety = FakeSafetySurface()
    runtime = build_runtime(
        events,
        safety=safety,
    )

    assert runtime.fan_telemetry() == {"telemetry_fresh": True}
    assert runtime.publish_fan_status("snapshot") == {"reason": "snapshot"}
    assert safety.telemetry_calls == 1
    assert safety.status_reasons == ["snapshot"]


def test_runtime_exposes_non_actuating_thermal_observation():
    events = []
    safety = FakeSafetySurface()
    reconciliation = FakeReconciliationSurface()
    runtime = build_runtime(
        events,
        safety=safety,
        fan_reconciliation=reconciliation,
    )

    telemetry = {"sample": 1}
    assert runtime.observe_thermal(telemetry) == {
        "recommended_profile": "automatic"
    }
    assert reconciliation.observe_calls == [telemetry]


def test_runtime_exposes_read_only_fan_status():
    events = []
    reads = []

    def read_status(*, max_age=30.0):
        reads.append(max_age)
        return {"active_profile": "automatic"}

    runtime = build_runtime(
        events,
        fan_status_reader=read_status,
    )

    assert runtime.read_fan_status(max_age=12.0) == {
        "active_profile": "automatic"
    }
    assert reads == [12.0]


def test_runtime_fan_status_read_fails_closed_without_reader():
    events = []
    runtime = build_runtime(events)

    assert runtime.read_fan_status() is None
