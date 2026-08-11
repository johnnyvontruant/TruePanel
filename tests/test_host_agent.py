import signal
import threading

import pytest

from truepanel.host import agent


class FakeRuntime:
    def __init__(
        self,
        events,
        *,
        fail_start=False,
        fail_shutdown=False,
    ):
        self.events = events
        self.fail_start = fail_start
        self.fail_shutdown = fail_shutdown

    def start(self):
        self.events.append("runtime.start")

        if self.fail_start:
            raise RuntimeError(
                "runtime start failure"
            )

    def shutdown(self):
        self.events.append("runtime.shutdown")

        if self.fail_shutdown:
            raise RuntimeError(
                "runtime shutdown failure"
            )


class ImmediateStopEvent:
    def __init__(self, events):
        self.events = events
        self.set_calls = 0

    def wait(self):
        self.events.append("wait")

    def set(self):
        self.set_calls += 1

    def is_set(self):
        return bool(self.set_calls)


def test_process_starts_waits_then_shuts_down():
    events = []
    runtime = FakeRuntime(events)
    stop_event = ImmediateStopEvent(events)

    process = agent.HostAgentProcess(
        lambda: runtime,
        stop_event=stop_event,
    )

    process.run()

    assert events == [
        "runtime.start",
        "wait",
        "runtime.shutdown",
    ]

    assert process.runtime is runtime


def test_process_shuts_down_when_start_fails():
    events = []
    runtime = FakeRuntime(
        events,
        fail_start=True,
    )

    process = agent.HostAgentProcess(
        lambda: runtime,
        stop_event=ImmediateStopEvent(events),
    )

    with pytest.raises(
        RuntimeError,
        match="runtime start failure",
    ):
        process.run()

    assert events == [
        "runtime.start",
        "runtime.shutdown",
    ]


def test_shutdown_request_sets_stop_event():
    stop_event = threading.Event()

    process = agent.HostAgentProcess(
        lambda: object(),
        stop_event=stop_event,
    )

    process.request_shutdown(
        signal.SIGTERM,
        None,
    )

    assert stop_event.is_set()


def test_signal_handlers_route_to_process(
    monkeypatch,
):
    installed = {}

    def fake_signal(signum, handler):
        installed[signum] = handler

    monkeypatch.setattr(
        agent.signal,
        "signal",
        fake_signal,
    )

    process = agent.HostAgentProcess(
        lambda: object()
    )

    agent.install_signal_handlers(
        process
    )

    assert installed[
        signal.SIGTERM
    ] == process.request_shutdown

    assert installed[
        signal.SIGINT
    ] == process.request_shutdown


def test_production_bootstrap_fails_closed():
    with pytest.raises(
        RuntimeError,
        match=(
            "Standalone Host Agent hardware "
            "bootstrap is not enabled yet"
        ),
    ):
        agent.build_production_runtime()


def test_main_installs_signals_before_run(
    monkeypatch,
):
    events = []

    class FakeProcess:
        def __init__(self, runtime_factory):
            del runtime_factory
            events.append("construct")

        def run(self):
            events.append("run")

    def install(process):
        del process
        events.append("signals")

    monkeypatch.setattr(
        agent,
        "HostAgentProcess",
        FakeProcess,
    )

    monkeypatch.setattr(
        agent,
        "install_signal_handlers",
        install,
    )

    agent.main()

    assert events == [
        "construct",
        "signals",
        "run",
    ]
