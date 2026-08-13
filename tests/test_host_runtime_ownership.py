import pytest

from truepanel.host.runtime import HostAgentRuntime


class FakeGuard:
    def __init__(self, events, *, fail=False):
        self.events = events
        self.fail = fail

    def acquire(self):
        self.events.append("ownership.acquire")
        if self.fail:
            raise RuntimeError("ownership busy")

    def release(self):
        self.events.append("ownership.release")


class FakeServer:
    def __init__(self, name, events, *, fail_start=False):
        self.name = name
        self.events = events
        self.fail_start = fail_start

    def start(self):
        self.events.append(f"{self.name}.start")
        if self.fail_start:
            raise RuntimeError(f"{self.name} failed")

    def stop(self):
        self.events.append(f"{self.name}.stop")


class FakeFanRuntime:
    def __init__(self, events):
        self.events = events

    def shutdown(self):
        self.events.append("fan_runtime.shutdown")


def make_runtime(events, guard, *, fail_fan=False):
    return HostAgentRuntime(
        fan_runtime=FakeFanRuntime(events),
        safety=object(),
        ownership_guard=guard,
        fan_server_factory=lambda: FakeServer(
            "fan_server",
            events,
            fail_start=fail_fan,
        ),
    )


def test_runtime_holds_ownership_for_privileged_lifetime():
    events = []
    runtime = make_runtime(
        events,
        FakeGuard(events),
    )

    runtime.start()
    runtime.shutdown()

    assert events == [
        "ownership.acquire",
        "fan_server.start",
        "fan_server.stop",
        "fan_runtime.shutdown",
        "ownership.release",
    ]


def test_losing_runtime_never_touches_fan_hardware():
    events = []
    runtime = make_runtime(
        events,
        FakeGuard(events, fail=True),
    )

    with pytest.raises(
        RuntimeError,
        match="ownership busy",
    ):
        runtime.start()

    runtime.shutdown()

    assert events == [
        "ownership.acquire",
    ]


def test_start_failure_restores_before_releasing_ownership():
    events = []
    runtime = make_runtime(
        events,
        FakeGuard(events),
        fail_fan=True,
    )

    with pytest.raises(
        RuntimeError,
        match="fan_server failed",
    ):
        runtime.start()

    assert events == [
        "ownership.acquire",
        "fan_server.start",
        "fan_server.stop",
        "fan_runtime.shutdown",
        "ownership.release",
    ]
