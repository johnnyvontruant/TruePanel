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
from .hooks import HostAgentApplicationHooks

RuntimeFactory = Callable[[], Any]


class HostAgentProcess:
    """Own one Host Agent runtime for the lifetime of a process."""

    def __init__(
        self,
        runtime_factory: RuntimeFactory,
        *,
        stop_event: threading.Event | None = None,
    ):
        self._runtime_factory = runtime_factory
        self._stop_event = (
            stop_event
            if stop_event is not None
            else threading.Event()
        )
        self._runtime = None

    @property
    def runtime(self) -> Any | None:
        return self._runtime

    @property
    def stop_event(self) -> threading.Event:
        return self._stop_event

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
        Start the Host Agent and block until shutdown is requested.

        Runtime shutdown is guaranteed after a successful construction,
        including when startup or the blocking wait raises.
        """

        runtime = self._runtime_factory()
        self._runtime = runtime

        try:
            runtime.start()
            self._stop_event.wait()
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
        application_hooks=(
            HostAgentApplicationHooks()
        ),
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
        build_production_runtime
    )

    install_signal_handlers(process)
    process.run()


if __name__ == "__main__":
    main()


__all__ = [
    "HostAgentProcess",
    "RuntimeFactory",
    "build_production_runtime",
    "install_signal_handlers",
    "main",
    "require_standalone_activation",
    "STANDALONE_PRODUCTION_ACTIVATED",
]
