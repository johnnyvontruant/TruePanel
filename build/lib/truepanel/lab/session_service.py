"""
Project Stargate Laboratory Session Service.

Provides a thin service layer around SessionRecorder so the CLI and
laboratory commands never interact with the recorder directly.
"""

from __future__ import annotations

from datetime import UTC, datetime

from truepanel.lab.commands import LabResult
from truepanel.lab.session import (
    SessionEvent,
    SessionRecorder,
    SessionSummary,
    LabSession,
)


class SessionService:
    """High-level interface for laboratory sessions."""

    def __init__(self) -> None:
        self._recorder = SessionRecorder()
        self._last_summary: SessionSummary | None = None

    def start_session(self) -> LabSession:
        self._last_summary = None
        return self._recorder.start()

    def stop_session(self) -> SessionSummary:
        summary = self._recorder.stop()
        self._last_summary = summary
        return summary

    def current_session(self) -> LabSession | None:
        return self._recorder.session

    def current_summary(self) -> SessionSummary | None:
        return self._last_summary

    def record_event(
        self,
        event: SessionEvent,
    ) -> None:
        self._recorder.record(event)

    def record_lab_result(
        self,
        result: LabResult,
        *,
        duration_ms: float = 0.0,
    ) -> None:
        self.record_event(
            SessionEvent(
                timestamp=datetime.now(UTC),
                command=result.command,
                success=result.success,
                duration_ms=duration_ms,
                capture_path=result.capture_path,
                metadata=dict(result.data),
            )
        )
