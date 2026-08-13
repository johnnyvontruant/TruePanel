"""
Standalone process lifecycle for the TruePanel Host Agent.

Hardware construction is intentionally injected. Production ownership remains
with the existing TruePanel runtime until the standalone bootstrap is completed
and explicitly activated.
"""

from __future__ import annotations

import signal
import threading
from collections.abc import Callable
from typing import Any

from truepanel.config.loader import load_config

from .bootstrap import build_host_agent_bootstrap
from .factory import build_host_agent_runtime_from_bootstrap

RuntimeFactory = Callable[[], Any]
DEFAULT_SERVICE_INTERVAL_SECONDS = 5.0


class HostAgentProcess:
    """Own one Host Agent runtime for the lifetime of a process."""

    def __init__(
        self,
        runtime_factory: RuntimeFactory,
        *,
        stop_event: threading.Event | None = None,
        service_interval_seconds: float = DEFAULT_SERVICE_INTERVAL_SECONDS,
    ):
        interval = float(service_interval_seconds)
        if interval <= 0:
            raise ValueError(
                "Host Agent service interval must be positive"
            )

        self._runtime_factory = runtime_factory
        self._stop_event = (
            stop_event
            if stop_event is not None
            else threading.Event()
        )
        self._service_interval_seconds = interval
        self._runtime = None

    @property
    def runtime(self) -> Any | None:
        return self._runtime

    @property
    def stop_event(self) -> threading.Event:
        return self._stop_event

    @property
    def service_interval_seconds(self) -> float:
        return self._service_interval_seconds

    def request_shutdown(
        self,
        signum: int | None = None,
        frame: Any | None = None,
    ) -> None:
        """Request an orderly Host Agent shutdown."""

        del signum
        del frame
        self._stop_event.set()

    def run(self) -> None:
        """
        Start the Host Agent and service it until shutdown is requested.

        The first service cycle runs immediately after runtime startup. Later
        cycles are separated by an interruptible stop-event wait. Runtime
        shutdown is guaranteed if startup or any service cycle raises.
        """

        runtime = self._runtime_factory()
        self._runtime = runtime

        try:
            runtime.start()

            while not self._stop_event.is_set():
                runtime.service_cycle()

                if self._stop_event.wait(
                    self._service_interval_seconds
                ):
                    break
        finally:
            runtime.shutdown()


def install_signal_handlers(
    process: HostAgentProcess,
) -> None:
    """Route SIGTERM and SIGINT into orderly Host Agent shutdown."""

    signal.signal(
        signal.SIGTERM,
        process.request_shutdown,
    )
    signal.signal(
        signal.SIGINT,
        process.request_shutdown,
    )


STANDALONE_PRODUCTION_ACTIVATED = False


def build_production_runtime() -> Any:
    """Construct the production Host runtime without starting it."""

    config = load_config()
    bootstrap = build_host_agent_bootstrap(
        config
    )

    return build_host_agent_runtime_from_bootstrap(
        bootstrap=bootstrap,
        owner_name="standalone-host-agent",
    )


def require_standalone_activation() -> None:
    """Fail closed until standalone Host ownership is explicitly activated."""

    if STANDALONE_PRODUCTION_ACTIVATED:
        return

    raise RuntimeError(
        "Standalone Host Agent activation is not enabled yet."
    )


def main() -> None:
    """Run the standalone Host Agent process only after explicit activation."""

    require_standalone_activation()

    process = HostAgentProcess(
        build_production_runtime,
        service_interval_seconds=(
            DEFAULT_SERVICE_INTERVAL_SECONDS
        ),
    )

    install_signal_handlers(process)
    process.run()


if __name__ == "__main__":
    main()


__all__ = [
    "DEFAULT_SERVICE_INTERVAL_SECONDS",
    "HostAgentProcess",
    "RuntimeFactory",
    "build_production_runtime",
    "install_signal_handlers",
    "main",
    "require_standalone_activation",
    "STANDALONE_PRODUCTION_ACTIVATED",
]
