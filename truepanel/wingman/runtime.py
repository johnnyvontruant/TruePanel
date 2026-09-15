"""Bounded local-inference lifecycle for Project WINGMAN."""

from __future__ import annotations

import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ProcessLike(Protocol):
    """Minimum process surface required by the WINGMAN lifecycle."""

    pid: int
    returncode: int | None

    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...


class WingmanRuntimeError(RuntimeError):
    """Base failure for bounded local-inference lifecycle."""


class WingmanResourceHold(WingmanRuntimeError):
    """Host resource gate refused model launch."""


class WingmanStartupError(WingmanRuntimeError):
    """The local inference process failed before becoming ready."""


@dataclass(frozen=True)
class HostResources:
    """Host resources considered before local model launch."""

    available_memory_bytes: int
    load_1m: float


@dataclass(frozen=True)
class RuntimePolicy:
    """Fail-closed lifecycle policy for the local model."""

    minimum_available_memory_bytes: int = 3 * 1024**3
    maximum_load_1m: float = 6.0
    startup_timeout_seconds: float = 30.0
    shutdown_timeout_seconds: float = 5.0
    poll_interval_seconds: float = 0.10


@dataclass(frozen=True)
class RuntimeObservation:
    """Read-only lifecycle state safe for diagnostics."""

    running: bool
    pid: int | None
    endpoint: str | None


@dataclass(frozen=True)
class LlamaRuntimeConfig:
    """Immutable llama.cpp launch contract."""

    server_path: Path
    model_path: Path
    host: str = "127.0.0.1"
    port: int = 18080
    context_size: int = 4096
    threads: int = 4
    parallel: int = 1

    @property
    def endpoint(self) -> str:
        return f"http://{self.host}:{self.port}/v1/chat/completions"

    @property
    def health_endpoint(self) -> str:
        return f"http://{self.host}:{self.port}/health"

    def command(self) -> tuple[str, ...]:
        if self.host not in {"127.0.0.1", "::1", "localhost"}:
            raise WingmanRuntimeError(
                f"refusing non-loopback inference bind: {self.host}"
            )

        return (
            str(self.server_path),
            "--model",
            str(self.model_path),
            "--host",
            self.host,
            "--port",
            str(self.port),
            "--ctx-size",
            str(self.context_size),
            "--threads",
            str(self.threads),
            "--threads-batch",
            str(self.threads),
            "--parallel",
            str(self.parallel),
        )


def read_host_resources() -> HostResources:
    """Read dependency-free Linux resource signals."""

    available_memory_bytes: int | None = None

    with open("/proc/meminfo", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("MemAvailable:"):
                available_memory_bytes = int(line.split()[1]) * 1024
                break

    if available_memory_bytes is None:
        raise WingmanRuntimeError("MemAvailable unavailable")

    with open("/proc/loadavg", encoding="utf-8") as handle:
        load_1m = float(handle.read().split()[0])

    return HostResources(
        available_memory_bytes=available_memory_bytes,
        load_1m=load_1m,
    )


def http_health_check(
    endpoint: str,
    *,
    timeout_seconds: float = 0.5,
) -> bool:
    """Return whether the loopback llama.cpp health endpoint is ready."""

    try:
        with urllib.request.urlopen(
            endpoint,
            timeout=timeout_seconds,
        ) as response:
            return response.status == 200
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
    ):
        return False


def enforce_resource_gate(
    resources: HostResources,
    policy: RuntimePolicy,
) -> None:
    """Fail closed when BattleStation lacks launch headroom."""

    if (
        resources.available_memory_bytes
        < policy.minimum_available_memory_bytes
    ):
        available_gib = (
            resources.available_memory_bytes / 1024**3
        )
        required_gib = (
            policy.minimum_available_memory_bytes / 1024**3
        )

        raise WingmanResourceHold(
            "insufficient memory headroom for local inference: "
            f"available={available_gib:.3f} GiB "
            f"required={required_gib:.3f} GiB"
        )

    if resources.load_1m > policy.maximum_load_1m:
        raise WingmanResourceHold(
            "host load exceeds local-inference launch policy: "
            f"load_1m={resources.load_1m:.3f} "
            f"maximum={policy.maximum_load_1m:.3f}"
        )


class WingmanLocalRuntime:
    """Own one short-lived llama.cpp process from spawn through reap."""

    def __init__(
        self,
        config: LlamaRuntimeConfig,
        *,
        policy: RuntimePolicy | None = None,
        resource_reader: Callable[[], HostResources] = read_host_resources,
        health_check: Callable[[str], bool] = http_health_check,
        process_factory: Callable[..., ProcessLike] = subprocess.Popen,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.policy = policy or RuntimePolicy()
        self._resource_reader = resource_reader
        self._health_check = health_check
        self._process_factory = process_factory
        self._monotonic = monotonic
        self._sleep = sleep
        self._process: ProcessLike | None = None

    @property
    def running(self) -> bool:
        process = self._process
        return process is not None and process.poll() is None

    @property
    def endpoint(self) -> str:
        if not self.running:
            raise WingmanRuntimeError(
                "local inference endpoint requested while runtime is stopped"
            )
        return self.config.endpoint

    @property
    def observation(self) -> RuntimeObservation:
        """Return lifecycle state without exposing the process object."""

        process = self._process
        running = process is not None and process.poll() is None

        return RuntimeObservation(
            running=running,
            pid=process.pid if running else None,
            endpoint=self.config.endpoint if running else None,
        )

    def start(self) -> str:
        if self.running:
            raise WingmanRuntimeError("local inference runtime already running")

        enforce_resource_gate(
            self._resource_reader(),
            self.policy,
        )

        command = self.config.command()

        if not self.config.server_path.is_file():
            raise WingmanStartupError(
                f"llama-server missing: {self.config.server_path}"
            )

        if not self.config.model_path.is_file():
            raise WingmanStartupError(
                f"model missing: {self.config.model_path}"
            )

        process = self._process_factory(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self._process = process

        deadline = self._monotonic() + self.policy.startup_timeout_seconds

        try:
            while self._monotonic() < deadline:
                returncode = process.poll()

                if returncode is not None:
                    raise WingmanStartupError(
                        "local inference process exited before readiness "
                        f"with code {returncode}"
                    )

                if self._health_check(self.config.health_endpoint):
                    return self.config.endpoint

                self._sleep(self.policy.poll_interval_seconds)

            raise WingmanStartupError(
                "local inference readiness timeout expired"
            )
        except BaseException:
            self.stop()
            raise

    def stop(self) -> None:
        process = self._process
        self._process = None

        if process is None:
            return

        if process.poll() is not None:
            process.wait()
            return

        process.terminate()

        try:
            process.wait(timeout=self.policy.shutdown_timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    def __enter__(self) -> WingmanLocalRuntime:
        self.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.stop()
