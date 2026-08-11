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


def test_runtime_starts_fan_then_lcd_server():
    events = []
    fan_runtime = FakeFanRuntime(events)
    fan_server = FakeServer(
        "fan_server",
        events,
    )
    lcd_server = FakeServer(
        "lcd_server",
        events,
    )

    runtime = HostAgentRuntime(
        fan_runtime=fan_runtime,
        fan_server_factory=lambda: fan_server,
        lcd_server_factory=lambda: lcd_server,
    )

    runtime.start()

    assert events == [
        "fan_server.start",
        "lcd_server.start",
    ]
    assert runtime.started is True
    assert runtime.fan_server is fan_server
    assert runtime.lcd_server is lcd_server


def test_runtime_allows_missing_servers():
    events = []
    fan_runtime = FakeFanRuntime(events)

    runtime = HostAgentRuntime(
        fan_runtime=fan_runtime,
        fan_server_factory=lambda: None,
        lcd_server_factory=lambda: None,
    )

    runtime.start()

    assert runtime.started is True
    assert runtime.fan_server is None
    assert runtime.lcd_server is None
    assert events == []


def test_runtime_start_is_idempotent():
    events = []
    fan_runtime = FakeFanRuntime(events)
    fan_server = FakeServer(
        "fan_server",
        events,
    )
    lcd_server = FakeServer(
        "lcd_server",
        events,
    )

    runtime = HostAgentRuntime(
        fan_runtime=fan_runtime,
        fan_server_factory=lambda: fan_server,
        lcd_server_factory=lambda: lcd_server,
    )

    runtime.start()
    runtime.start()

    assert fan_server.start_calls == 1
    assert lcd_server.start_calls == 1


def test_shutdown_stops_lcd_then_fan_then_runtime():
    events = []
    fan_runtime = FakeFanRuntime(events)
    fan_server = FakeServer(
        "fan_server",
        events,
    )
    lcd_server = FakeServer(
        "lcd_server",
        events,
    )

    runtime = HostAgentRuntime(
        fan_runtime=fan_runtime,
        fan_server_factory=lambda: fan_server,
        lcd_server_factory=lambda: lcd_server,
    )

    runtime.start()
    events.clear()

    runtime.shutdown()

    assert events == [
        "lcd_server.stop",
        "fan_server.stop",
        "fan_runtime.shutdown",
    ]

    assert runtime.started is False
    assert runtime.fan_server is None
    assert runtime.lcd_server is None


def test_shutdown_is_idempotent():
    events = []
    fan_runtime = FakeFanRuntime(events)
    fan_server = FakeServer(
        "fan_server",
        events,
    )
    lcd_server = FakeServer(
        "lcd_server",
        events,
    )

    runtime = HostAgentRuntime(
        fan_runtime=fan_runtime,
        fan_server_factory=lambda: fan_server,
        lcd_server_factory=lambda: lcd_server,
    )

    runtime.start()

    runtime.shutdown()
    runtime.shutdown()

    assert lcd_server.stop_calls == 1
    assert fan_server.stop_calls == 1
    assert fan_runtime.shutdown_calls == 1


def test_lcd_start_failure_rolls_back_host_runtime():
    events = []
    fan_runtime = FakeFanRuntime(events)

    fan_server = FakeServer(
        "fan_server",
        events,
    )

    lcd_server = FakeServer(
        "lcd_server",
        events,
        fail_start=True,
    )

    runtime = HostAgentRuntime(
        fan_runtime=fan_runtime,
        fan_server_factory=lambda: fan_server,
        lcd_server_factory=lambda: lcd_server,
    )

    with pytest.raises(
        RuntimeError,
        match="lcd_server start failure",
    ):
        runtime.start()

    assert events == [
        "fan_server.start",
        "lcd_server.start",
        "lcd_server.stop",
        "fan_server.stop",
        "fan_runtime.shutdown",
    ]

    assert runtime.started is False


def test_fan_start_failure_restores_runtime():
    events = []
    fan_runtime = FakeFanRuntime(events)

    fan_server = FakeServer(
        "fan_server",
        events,
        fail_start=True,
    )

    runtime = HostAgentRuntime(
        fan_runtime=fan_runtime,
        fan_server_factory=lambda: fan_server,
        lcd_server_factory=lambda: None,
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


def test_shutdown_continues_after_server_failure():
    events = []
    fan_runtime = FakeFanRuntime(events)

    fan_server = FakeServer(
        "fan_server",
        events,
    )

    lcd_server = FakeServer(
        "lcd_server",
        events,
        fail_stop=True,
    )

    runtime = HostAgentRuntime(
        fan_runtime=fan_runtime,
        fan_server_factory=lambda: fan_server,
        lcd_server_factory=lambda: lcd_server,
    )

    runtime.start()
    events.clear()

    runtime.shutdown()

    assert events == [
        "lcd_server.stop",
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

    runtime = HostAgentRuntime(
        fan_runtime=fan_runtime,
        fan_server_factory=lambda: None,
        lcd_server_factory=lambda: None,
    )

    runtime.start()
    runtime.shutdown()

    assert events == [
        "fan_runtime.shutdown",
    ]
    assert runtime.started is False


def test_runtime_cannot_restart_after_shutdown():
    events = []

    runtime = HostAgentRuntime(
        fan_runtime=FakeFanRuntime(events),
        fan_server_factory=lambda: None,
        lcd_server_factory=lambda: None,
    )

    runtime.start()
    runtime.shutdown()

    with pytest.raises(
        RuntimeError,
        match="cannot restart after shutdown",
    ):
        runtime.start()
