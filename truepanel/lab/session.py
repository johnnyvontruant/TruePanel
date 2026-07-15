"""
Project Stargate Laboratory Session Recorder.

Sessions record laboratory activity without knowing anything about
individual laboratory commands.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import uuid


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class SessionEvent:
    timestamp: datetime
    command: str
    success: bool
    duration_ms: float
    capture_path: str = ""
    metadata: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        return payload


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    commands: int
    successes: int
    failures: int
    captures: int

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["started_at"] = self.started_at.isoformat()
        payload["completed_at"] = self.completed_at.isoformat()
        return payload


@dataclass
class LabSession:
    session_id: str
    started_at: datetime
    events: list[SessionEvent] = field(default_factory=list)
    completed_at: datetime | None = None

    @property
    def active(self) -> bool:
        return self.completed_at is None

    def as_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat()
                if self.completed_at
                else None
            ),
            "events": [
                event.as_dict()
                for event in self.events
            ],
        }


class SessionRecorder:
    """In-memory laboratory session recorder."""

    def __init__(self):
        self._session: LabSession | None = None

    @property
    def session(self) -> LabSession | None:
        return self._session

    def start(self) -> LabSession:
        if self._session and self._session.active:
            raise RuntimeError("session already active")

        self._session = LabSession(
            session_id=uuid.uuid4().hex[:12],
            started_at=_utc_now(),
        )

        return self._session

    def record(self, event: SessionEvent) -> None:
        if self._session is None:
            raise RuntimeError("no active session")

        if not self._session.active:
            raise RuntimeError("session already closed")

        self._session.events.append(event)

    def stop(self) -> SessionSummary:
        if self._session is None:
            raise RuntimeError("no active session")

        if self._session.completed_at is not None:
            raise RuntimeError("session already closed")

        self._session.completed_at = _utc_now()

        events = self._session.events

        return SessionSummary(
            session_id=self._session.session_id,
            started_at=self._session.started_at,
            completed_at=self._session.completed_at,
            duration_seconds=(
                self._session.completed_at
                - self._session.started_at
            ).total_seconds(),
            commands=len(events),
            successes=sum(
                event.success
                for event in events
            ),
            failures=sum(
                not event.success
                for event in events
            ),
            captures=sum(
                bool(event.capture_path)
                for event in events
            ),
        )
