"""
Canonical execution events for Project Stargate.

Execution events describe completed execution attempts. They are immutable,
serializable, and independent of the CLI, session recorder, discovery engine,
or future dashboards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Callable, Iterable

from .execution import ExecutionResult


class ExecutionEventType(Enum):
    DENIED = "denied"
    SIMULATED = "simulated"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class ExecutionEvent:
    timestamp: datetime
    event_type: ExecutionEventType
    request_id: str
    command: str
    opcode: int
    controller_family: str
    mode: str
    success: bool
    duration_ms: float
    decision: str
    message: str
    data: object = None
    capture_path: str = ""
    metadata: dict = field(default_factory=dict)
    error: str = ""

    @property
    def opcode_hex(self):
        return f"0x{self.opcode:02X}"

    @classmethod
    def from_result(
        cls,
        result: ExecutionResult,
        *,
        controller_family: str,
        timestamp: datetime | None = None,
    ):
        if not isinstance(result, ExecutionResult):
            raise TypeError(
                "result must be an ExecutionResult"
            )

        if (
            not controller_family
            or not controller_family.strip()
        ):
            raise ValueError(
                "controller_family is required"
            )

        event_type = ExecutionEventType(
            result.status.value
        )

        mode = str(
            result.metadata.get(
                "mode",
                "unknown",
            )
        )

        return cls(
            timestamp=timestamp or datetime.now(UTC),
            event_type=event_type,
            request_id=result.request_id,
            command=result.command,
            opcode=result.opcode,
            controller_family=controller_family.strip(),
            mode=mode,
            success=result.success,
            duration_ms=result.duration_ms,
            decision=result.decision.reason.value,
            message=result.decision.message,
            data=result.data,
            capture_path=result.capture_path,
            metadata=dict(result.metadata),
            error=result.error,
        )

    def as_dict(self):
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "request_id": self.request_id,
            "command": self.command,
            "opcode": self.opcode,
            "opcode_hex": self.opcode_hex,
            "controller_family": self.controller_family,
            "mode": self.mode,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "decision": self.decision,
            "message": self.message,
            "data": self.data,
            "capture_path": self.capture_path,
            "metadata": dict(self.metadata),
            "error": self.error,
        }


class ExecutionEventListener:
    """
    Interface for execution-event consumers.
    """

    def handle(self, event: ExecutionEvent):
        raise NotImplementedError


class CallableExecutionEventListener(
    ExecutionEventListener
):
    def __init__(
        self,
        callback: Callable[[ExecutionEvent], None],
    ):
        if not callable(callback):
            raise TypeError(
                "callback must be callable"
            )

        self.callback = callback

    def handle(self, event):
        self.callback(event)


class ExecutionEventBus:
    """
    Synchronous in-process event dispatcher.

    Listener failures are isolated so telemetry cannot alter the result of an
    already completed execution.
    """

    def __init__(
        self,
        listeners: Iterable[
            ExecutionEventListener | Callable
        ] = (),
    ):
        self._listeners = []

        for listener in listeners:
            self.subscribe(listener)

    def subscribe(self, listener):
        normalized = self._normalize_listener(
            listener
        )

        if normalized not in self._listeners:
            self._listeners.append(normalized)

        return normalized

    def unsubscribe(self, listener):
        try:
            self._listeners.remove(listener)
        except ValueError:
            return False

        return True

    def publish(self, event):
        if not isinstance(event, ExecutionEvent):
            raise TypeError(
                "event must be an ExecutionEvent"
            )

        failures = []

        for listener in tuple(self._listeners):
            try:
                listener.handle(event)
            except Exception as exc:
                failures.append(
                    {
                        "listener": (
                            type(listener).__name__
                        ),
                        "exception_type": (
                            type(exc).__name__
                        ),
                        "error": str(exc),
                    }
                )

        return tuple(failures)

    @property
    def listeners(self):
        return tuple(self._listeners)

    def __len__(self):
        return len(self._listeners)

    @staticmethod
    def _normalize_listener(listener):
        if isinstance(
            listener,
            ExecutionEventListener,
        ):
            return listener

        if callable(listener):
            return CallableExecutionEventListener(
                listener
            )

        raise TypeError(
            (
                "listener must be an "
                "ExecutionEventListener or callable"
            )
        )


class ExecutionEventRecorder(
    ExecutionEventListener
):
    """
    In-memory event recorder useful for sessions, tests, and diagnostics.
    """

    def __init__(self, max_events=1000):
        if max_events <= 0:
            raise ValueError(
                "max_events must be greater than zero"
            )

        self.max_events = int(max_events)
        self._events = []

    def handle(self, event):
        if not isinstance(event, ExecutionEvent):
            raise TypeError(
                "event must be an ExecutionEvent"
            )

        self._events.append(event)

        overflow = (
            len(self._events)
            - self.max_events
        )

        if overflow > 0:
            del self._events[:overflow]

    @property
    def events(self):
        return tuple(self._events)

    def clear(self):
        self._events.clear()

    def latest(self):
        if not self._events:
            return None

        return self._events[-1]

    def by_command(self, command):
        return tuple(
            event
            for event in self._events
            if event.command == command
        )

    def failures(self):
        return tuple(
            event
            for event in self._events
            if not event.success
        )

    def as_dict(self):
        return {
            "event_count": len(self._events),
            "events": [
                event.as_dict()
                for event in self._events
            ],
        }

    def __len__(self):
        return len(self._events)
