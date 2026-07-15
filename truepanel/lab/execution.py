"""
Project Stargate laboratory execution engine.

The engine coordinates approved operations but does not define safety policy.
Every request must pass through an ExecutionInterlock before an adapter can be
invoked.

The engine is controller-neutral. Hardware-specific behavior belongs in an
ExecutionAdapter implementation.
"""

from dataclasses import dataclass, field
from enum import Enum
import time

from .interlock import (
    ExecutionMode,
    InterlockDecision,
    InterlockReason,
)


class ExecutionStatus(Enum):
    DENIED = "denied"
    SIMULATED = "simulated"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class AdapterResponse:
    """
    Normalized response returned by an execution adapter.
    """

    data: object = None
    capture_path: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionResult:
    """
    Complete outcome of one execution request.
    """

    request_id: str
    command: str
    opcode: int
    status: ExecutionStatus
    success: bool
    duration_ms: float
    decision: InterlockDecision
    data: object = None
    capture_path: str = ""
    metadata: dict = field(default_factory=dict)
    error: str = ""

    @property
    def denied(self):
        return self.status is ExecutionStatus.DENIED

    @property
    def simulated(self):
        return self.status is ExecutionStatus.SIMULATED

    @property
    def executed_live(self):
        return self.status in {
            ExecutionStatus.SUCCEEDED,
            ExecutionStatus.FAILED,
        }

    def as_dict(self):
        return {
            "request_id": self.request_id,
            "command": self.command,
            "opcode": self.opcode,
            "status": self.status.value,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "decision": self.decision.reason.value,
            "message": self.decision.message,
            "data": self.data,
            "capture_path": self.capture_path,
            "metadata": dict(self.metadata),
            "error": self.error,
        }


class ExecutionAdapter:
    """
    Interface implemented by controller-specific execution adapters.
    """

    def execute(self, request):
        raise NotImplementedError


class CallableExecutionAdapter(ExecutionAdapter):
    """
    Small adapter useful for integration code and tests.

    The supplied callable receives the ExecutionRequest and may return either
    an AdapterResponse or a raw data value.
    """

    def __init__(self, executor):
        if not callable(executor):
            raise TypeError("executor must be callable")

        self.executor = executor

    def execute(self, request):
        return self.executor(request)


class ExecutionEngine:
    def __init__(
        self,
        interlock,
        adapter,
        *,
        session_service=None,
        clock=None,
    ):
        if interlock is None:
            raise ValueError("interlock is required")

        if adapter is None:
            raise ValueError("adapter is required")

        if not hasattr(adapter, "execute"):
            raise TypeError(
                "adapter must provide an execute(request) method"
            )

        self.interlock = interlock
        self.adapter = adapter
        self.session_service = session_service
        self.clock = clock or time.perf_counter

    def execute(
        self,
        request,
        *,
        authorization=None,
        controller_family=None,
    ):
        """
        Evaluate and execute one laboratory request.

        Denied and simulated requests never invoke the adapter.
        """

        started_at = self.clock()

        decision = self.interlock.evaluate(
            request,
            authorization=authorization,
            controller_family=controller_family,
        )

        if not decision.allowed:
            result = ExecutionResult(
                request_id=request.request_id,
                command=request.name,
                opcode=request.opcode,
                status=ExecutionStatus.DENIED,
                success=False,
                duration_ms=self._elapsed_ms(started_at),
                decision=decision,
                metadata={
                    "mode": request.mode.value,
                    "danger_level": (
                        request.danger_level.value
                    ),
                    "known_opcode": request.known_opcode,
                },
                error=decision.message,
            )
            self._record(result)
            return result

        if (
            request.mode is ExecutionMode.SIMULATION
            or decision.simulation_only
        ):
            result = ExecutionResult(
                request_id=request.request_id,
                command=request.name,
                opcode=request.opcode,
                status=ExecutionStatus.SIMULATED,
                success=True,
                duration_ms=self._elapsed_ms(started_at),
                decision=decision,
                data={
                    "simulated": True,
                    "opcode": request.opcode,
                    "payload": request.payload.hex(),
                },
                metadata={
                    "mode": request.mode.value,
                    "danger_level": (
                        request.danger_level.value
                    ),
                    "known_opcode": request.known_opcode,
                },
            )
            self._record(result)
            return result

        try:
            adapter_response = self._normalize_response(
                self.adapter.execute(request)
            )
        except Exception as exc:
            result = ExecutionResult(
                request_id=request.request_id,
                command=request.name,
                opcode=request.opcode,
                status=ExecutionStatus.FAILED,
                success=False,
                duration_ms=self._elapsed_ms(started_at),
                decision=decision,
                metadata={
                    "mode": request.mode.value,
                    "danger_level": (
                        request.danger_level.value
                    ),
                    "known_opcode": request.known_opcode,
                    "exception_type": type(exc).__name__,
                },
                error=str(exc),
            )
            self._record(result)
            return result

        self.interlock.record_execution(request)

        metadata = {
            "mode": request.mode.value,
            "danger_level": request.danger_level.value,
            "known_opcode": request.known_opcode,
        }
        metadata.update(adapter_response.metadata)

        result = ExecutionResult(
            request_id=request.request_id,
            command=request.name,
            opcode=request.opcode,
            status=ExecutionStatus.SUCCEEDED,
            success=True,
            duration_ms=self._elapsed_ms(started_at),
            decision=decision,
            data=adapter_response.data,
            capture_path=adapter_response.capture_path,
            metadata=metadata,
        )
        self._record(result)
        return result

    def _elapsed_ms(self, started_at):
        return max(
            0.0,
            (self.clock() - started_at) * 1000.0,
        )

    @staticmethod
    def _normalize_response(response):
        if isinstance(response, AdapterResponse):
            return response

        return AdapterResponse(data=response)

    def _record(self, result):
        """
        Record the result when a compatible session service is active.

        Session recording must never change execution success or failure.
        """

        if self.session_service is None:
            return

        current_session = getattr(
            self.session_service,
            "current_session",
            lambda: None,
        )()

        if current_session is None or not current_session.active:
            return

        record_method = getattr(
            self.session_service,
            "record_execution_result",
            None,
        )

        if callable(record_method):
            record_method(result)
            return

        self._record_as_session_event(result)

    def _record_as_session_event(self, result):
        """
        Compatibility path for the existing SessionService API.
        """

        try:
            from datetime import UTC, datetime

            from .session import SessionEvent
        except ImportError:
            return

        record_event = getattr(
            self.session_service,
            "record_event",
            None,
        )

        if not callable(record_event):
            return

        metadata = dict(result.metadata)
        metadata.update(
            {
                "request_id": result.request_id,
                "opcode": result.opcode,
                "status": result.status.value,
                "decision": result.decision.reason.value,
                "error": result.error,
            }
        )

        event = SessionEvent(
            timestamp=datetime.now(UTC),
            command=result.command,
            success=result.success,
            duration_ms=result.duration_ms,
            capture_path=result.capture_path,
            metadata=metadata,
        )

        try:
            record_event(event)
        except (RuntimeError, TypeError):
            # Session recording is observational. A recorder mismatch must
            # never retroactively alter the execution result.
            return


def denied_decision(message="Execution denied"):
    """
    Convenience helper for adapters and tests requiring a denial decision.
    """

    return InterlockDecision.deny(
        InterlockReason.INVALID_REQUEST,
        message,
    )
