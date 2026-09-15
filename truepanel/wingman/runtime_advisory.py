"""On-demand local-runtime orchestration for Project WINGMAN."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

from .contracts import GroundingSource, WingmanMode
from .provider import LlamaCppProvider, WingmanProvider
from .runtime import WingmanLocalRuntime, WingmanRuntimeError
from .service import WingmanAdvisoryService, WingmanServiceResult

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeAdvisoryObservation:
    """Read-only observation of one bounded advisory attempt."""

    runtime_started: bool
    model_invoked: bool
    runtime_reaped: bool


class WingmanRuntimeAdvisory:
    """Own the complete local inference lifecycle for one advisory request."""

    def __init__(
        self,
        runtime: WingmanLocalRuntime,
        *,
        provider_factory: Callable[[str], WingmanProvider] | None = None,
        source_limit: int = 6,
    ) -> None:
        self.runtime = runtime
        self.source_limit = source_limit
        self._provider_factory = provider_factory or self._default_provider
        self._lock = threading.Lock()

    @staticmethod
    def _default_provider(endpoint: str) -> WingmanProvider:
        return LlamaCppProvider(
            endpoint=endpoint,
            model="wingman-local",
            timeout_seconds=60.0,
            max_tokens=512,
            allow_remote=False,
        )

    @staticmethod
    def _unavailable(error: str) -> WingmanServiceResult:
        return WingmanServiceResult(
            status="MODEL_UNAVAILABLE",
            advisory=None,
            source_ids=(),
            errors=(error,),
        )

    def advise(
        self,
        *,
        mode: WingmanMode,
        question: str,
        sources: tuple[GroundingSource, ...],
    ) -> tuple[WingmanServiceResult, RuntimeAdvisoryObservation]:
        """Run one advisory with fail-closed lifecycle ownership."""

        if not self._lock.acquire(blocking=False):
            return (
                self._unavailable("InferenceBusy"),
                RuntimeAdvisoryObservation(
                    runtime_started=False,
                    model_invoked=False,
                    runtime_reaped=True,
                ),
            )

        runtime_started = False

        try:
            try:
                self.runtime.start()
                runtime_started = True
            except (OSError, RuntimeError, WingmanRuntimeError) as exc:
                LOGGER.warning(
                    "WINGMAN local inference launch unavailable: %s",
                    exc,
                )
                return (
                    self._unavailable(type(exc).__name__),
                    RuntimeAdvisoryObservation(
                        runtime_started=False,
                        model_invoked=False,
                        runtime_reaped=not self.runtime.running,
                    ),
                )

            provider = self._provider_factory(self.runtime.endpoint)
            service = WingmanAdvisoryService(
                provider,
                source_limit=self.source_limit,
            )

            result = service.advise(
                mode=mode,
                question=question,
                sources=sources,
            )
        finally:
            if runtime_started or self.runtime.running:
                self.runtime.stop()

            self._lock.release()

        return (
            result,
            RuntimeAdvisoryObservation(
                runtime_started=True,
                model_invoked=True,
                runtime_reaped=not self.runtime.running,
            ),
        )


__all__ = [
    "RuntimeAdvisoryObservation",
    "WingmanRuntimeAdvisory",
]
