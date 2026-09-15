from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from truepanel.wingman.runtime import (
    HostResources,
    LlamaRuntimeConfig,
    RuntimePolicy,
    WingmanLocalRuntime,
    WingmanResourceHold,
    WingmanRuntimeError,
    WingmanStartupError,
    enforce_resource_gate,
)

GIB = 1024**3


class FakeProcess:
    def __init__(
        self,
        *,
        pid: int = 4242,
        returncode: int | None = None,
        timeout_on_terminate: bool = False,
    ) -> None:
        self.pid = pid
        self.returncode = returncode
        self.timeout_on_terminate = timeout_on_terminate
        self.terminated = False
        self.killed = False
        self.waited = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        self.waited = True

        if (
            timeout is not None
            and self.timeout_on_terminate
            and not self.killed
        ):
            raise subprocess.TimeoutExpired(
                cmd="llama-server",
                timeout=timeout,
            )

        if self.returncode is None:
            self.returncode = 0

        return self.returncode


@pytest.fixture
def runtime_files(tmp_path: Path) -> tuple[Path, Path]:
    server = tmp_path / "llama-server"
    model = tmp_path / "granite.gguf"

    server.write_text("fake server", encoding="utf-8")
    model.write_text("fake model", encoding="utf-8")

    return server, model


def config_for(
    runtime_files: tuple[Path, Path],
    *,
    host: str = "127.0.0.1",
) -> LlamaRuntimeConfig:
    server, model = runtime_files

    return LlamaRuntimeConfig(
        server_path=server,
        model_path=model,
        host=host,
    )


def healthy_resources() -> HostResources:
    return HostResources(
        available_memory_bytes=4 * GIB,
        load_1m=1.0,
    )


def test_resource_gate_rejects_low_memory():
    policy = RuntimePolicy(
        minimum_available_memory_bytes=3 * GIB
    )

    with pytest.raises(
        WingmanResourceHold,
        match="memory",
    ):
        enforce_resource_gate(
            HostResources(
                available_memory_bytes=2 * GIB,
                load_1m=0.5,
            ),
            policy,
        )


def test_resource_gate_rejects_high_load():
    policy = RuntimePolicy(maximum_load_1m=4.0)

    with pytest.raises(
        WingmanResourceHold,
        match="load",
    ):
        enforce_resource_gate(
            HostResources(
                available_memory_bytes=4 * GIB,
                load_1m=5.0,
            ),
            policy,
        )


def test_config_refuses_non_loopback_bind(runtime_files):
    config = config_for(
        runtime_files,
        host="0.0.0.0",
    )

    with pytest.raises(
        WingmanRuntimeError,
        match="non-loopback",
    ):
        config.command()


def test_runtime_reaches_ready_and_exposes_endpoint(runtime_files):
    process = FakeProcess()
    seen_commands = []

    def process_factory(command, **kwargs):
        seen_commands.append((command, kwargs))
        return process

    runtime = WingmanLocalRuntime(
        config_for(runtime_files),
        resource_reader=healthy_resources,
        health_check=lambda endpoint: True,
        process_factory=process_factory,
    )

    endpoint = runtime.start()

    assert endpoint.endswith("/v1/chat/completions")
    assert runtime.endpoint == endpoint
    assert runtime.running is True
    assert seen_commands
    assert "--host" in seen_commands[0][0]
    assert "127.0.0.1" in seen_commands[0][0]

    runtime.stop()

    assert process.terminated is True
    assert process.waited is True
    assert runtime.running is False


def test_startup_timeout_always_reaps_process(runtime_files):
    process = FakeProcess()
    clock = iter((0.0, 0.0, 0.2, 0.4, 0.6))

    runtime = WingmanLocalRuntime(
        config_for(runtime_files),
        policy=RuntimePolicy(
            startup_timeout_seconds=0.5,
            poll_interval_seconds=0.0,
        ),
        resource_reader=healthy_resources,
        health_check=lambda endpoint: False,
        process_factory=lambda *args, **kwargs: process,
        monotonic=lambda: next(clock),
        sleep=lambda seconds: None,
    )

    with pytest.raises(
        WingmanStartupError,
        match="readiness timeout",
    ):
        runtime.start()

    assert process.terminated is True
    assert process.waited is True
    assert runtime.running is False


def test_early_process_exit_is_reaped(runtime_files):
    process = FakeProcess(returncode=7)

    runtime = WingmanLocalRuntime(
        config_for(runtime_files),
        resource_reader=healthy_resources,
        health_check=lambda endpoint: False,
        process_factory=lambda *args, **kwargs: process,
    )

    with pytest.raises(
        WingmanStartupError,
        match="code 7",
    ):
        runtime.start()

    assert process.waited is True
    assert runtime.running is False


def test_shutdown_escalates_from_terminate_to_kill(runtime_files):
    process = FakeProcess(timeout_on_terminate=True)

    runtime = WingmanLocalRuntime(
        config_for(runtime_files),
        resource_reader=healthy_resources,
        health_check=lambda endpoint: True,
        process_factory=lambda *args, **kwargs: process,
    )

    runtime.start()
    runtime.stop()

    assert process.terminated is True
    assert process.killed is True
    assert process.waited is True


def test_context_manager_cleans_up_after_caller_exception(runtime_files):
    process = FakeProcess()

    runtime = WingmanLocalRuntime(
        config_for(runtime_files),
        resource_reader=healthy_resources,
        health_check=lambda endpoint: True,
        process_factory=lambda *args, **kwargs: process,
    )

    with pytest.raises(ValueError, match="boom"), runtime:
        raise ValueError("boom")

    assert process.terminated is True
    assert process.waited is True
    assert runtime.running is False


def test_endpoint_is_unavailable_when_stopped(runtime_files):
    runtime = WingmanLocalRuntime(
        config_for(runtime_files),
        resource_reader=healthy_resources,
        health_check=lambda endpoint: True,
    )

    with pytest.raises(
        WingmanRuntimeError,
        match="stopped",
    ):
        _ = runtime.endpoint


class FakeHttpResponse:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


def test_http_health_check_accepts_http_200(monkeypatch):
    from truepanel.wingman.runtime import http_health_check

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda endpoint, timeout: FakeHttpResponse(200),
    )

    assert http_health_check("http://127.0.0.1:18080/health") is True


def test_http_health_check_rejects_non_200(monkeypatch):
    from truepanel.wingman.runtime import http_health_check

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda endpoint, timeout: FakeHttpResponse(503),
    )

    assert http_health_check("http://127.0.0.1:18080/health") is False


def test_http_health_check_fails_closed_on_connection_error(monkeypatch):
    import urllib.error

    from truepanel.wingman.runtime import http_health_check

    def unavailable(endpoint, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(
        "urllib.request.urlopen",
        unavailable,
    )

    assert http_health_check("http://127.0.0.1:18080/health") is False


def test_observation_is_empty_when_stopped(runtime_files):
    runtime = WingmanLocalRuntime(
        config_for(runtime_files),
        resource_reader=healthy_resources,
        health_check=lambda endpoint: True,
    )

    observation = runtime.observation

    assert observation.running is False
    assert observation.pid is None
    assert observation.endpoint is None


def test_observation_exposes_only_live_runtime_state(runtime_files):
    process = FakeProcess(pid=8675309)

    runtime = WingmanLocalRuntime(
        config_for(runtime_files),
        resource_reader=healthy_resources,
        health_check=lambda endpoint: True,
        process_factory=lambda *args, **kwargs: process,
    )

    runtime.start()

    observation = runtime.observation

    assert observation.running is True
    assert observation.pid == 8675309
    assert observation.endpoint == runtime.endpoint

    runtime.stop()

    stopped = runtime.observation

    assert stopped.running is False
    assert stopped.pid is None
    assert stopped.endpoint is None
