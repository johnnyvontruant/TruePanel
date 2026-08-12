"""
Lifecycle ownership for TruePanel privileged host services.

HostAgentRuntime groups the local command servers and fan-control runtime behind
one lifecycle boundary. It does not change command protocols, hardware policy,
or authorization rules.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

LOGGER = logging.getLogger(__name__)


class HostAgentRuntime:
    """
    Own the lifecycle of TruePanel's privileged local host services.

    Server factories remain outside this class for now so existing hardware
    construction and command wiring can be migrated independently.
    """

    def __init__(
        self,
        *,
        fan_runtime: Any,
        safety: Any,
        fan_server_factory: Callable[[], Any | None],
        lcd_server_factory: Callable[[], Any | None],
        fan_reconciliation: Any | None = None,
    ):
        self._fan_runtime = fan_runtime
        self._safety = safety
        self._fan_reconciliation = fan_reconciliation
        self._fan_server_factory = fan_server_factory
        self._lcd_server_factory = lcd_server_factory

        self._fan_server = None
        self._lcd_server = None
        self._started = False
        self._shutdown = False

    @property
    def safety(self) -> Any:
        """Return the Host Agent safety coordinator."""

        return self._safety

    def reconcile_fans(self) -> Any | None:
        """Run one Host-owned fan/thermal reconciliation cycle."""

        if self._fan_reconciliation is None:
            return None

        return self._fan_reconciliation.reconcile()

    @property
    def started(self) -> bool:
        return self._started

    @property
    def fan_server(self) -> Any | None:
        return self._fan_server

    @property
    def lcd_server(self) -> Any | None:
        return self._lcd_server

    def start(self) -> None:
        """
        Start host command services.

        Starting twice is harmless. If startup fails part-way through, all
        resources already acquired by this runtime are released before the
        original exception is re-raised.
        """

        if self._started:
            return

        if self._shutdown:
            raise RuntimeError(
                "HostAgentRuntime cannot restart after shutdown"
            )

        try:
            self._fan_server = (
                self._fan_server_factory()
            )

            if self._fan_server is not None:
                self._fan_server.start()

            self._lcd_server = (
                self._lcd_server_factory()
            )

            if self._lcd_server is not None:
                self._lcd_server.start()

            self._started = True
        except Exception:
            LOGGER.exception(
                "Host Agent startup failed"
            )

            self.shutdown()
            raise

    def shutdown(self) -> None:
        """
        Stop command services and restore the fan runtime.

        Socket services are stopped before fan-control shutdown so no new
        commands can enter while automatic fan restoration is occurring.
        """

        if self._shutdown:
            return

        self._shutdown = True

        if self._lcd_server is not None:
            try:
                self._lcd_server.stop()
            except Exception:
                LOGGER.exception(
                    "LCD command server shutdown failed"
                )
            finally:
                self._lcd_server = None

        if self._fan_server is not None:
            try:
                self._fan_server.stop()
            except Exception:
                LOGGER.exception(
                    "Fan command server shutdown failed"
                )
            finally:
                self._fan_server = None

        try:
            self._fan_runtime.shutdown()
        except Exception:
            LOGGER.exception(
                "Fan-control runtime shutdown failed"
            )

        self._started = False


__all__ = [
    "HostAgentRuntime",
]
