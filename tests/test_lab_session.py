from datetime import UTC, datetime

import pytest

from truepanel.lab.session import (
    SessionEvent,
    SessionRecorder,
)


def make_event(
    command="discover",
    success=True,
    capture="",
):
    return SessionEvent(
        timestamp=datetime.now(UTC),
        command=command,
        success=success,
        duration_ms=50.0,
        capture_path=capture,
    )


def test_start_creates_active_session():
    recorder = SessionRecorder()

    session = recorder.start()

    assert session.active
    assert len(session.session_id) == 12
    assert recorder.session is session


def test_cannot_start_twice():
    recorder = SessionRecorder()

    recorder.start()

    with pytest.raises(RuntimeError):
        recorder.start()


def test_record_appends_events():
    recorder = SessionRecorder()
    recorder.start()

    recorder.record(make_event())
    recorder.record(make_event(command="repeat"))

    assert len(recorder.session.events) == 2


def test_stop_returns_summary():
    recorder = SessionRecorder()
    recorder.start()

    recorder.record(make_event())
    recorder.record(make_event(success=False))

    summary = recorder.stop()

    assert summary.commands == 2
    assert summary.successes == 1
    assert summary.failures == 1


def test_capture_count():
    recorder = SessionRecorder()
    recorder.start()

    recorder.record(make_event(capture="a.log"))
    recorder.record(make_event(capture=""))
    recorder.record(make_event(capture="b.log"))

    summary = recorder.stop()

    assert summary.captures == 2


def test_stop_closes_session():
    recorder = SessionRecorder()
    session = recorder.start()

    recorder.stop()

    assert not session.active


def test_record_after_stop_fails():
    recorder = SessionRecorder()
    recorder.start()
    recorder.stop()

    with pytest.raises(RuntimeError):
        recorder.record(make_event())


def test_stop_twice_fails():
    recorder = SessionRecorder()
    recorder.start()
    recorder.stop()

    with pytest.raises(RuntimeError):
        recorder.stop()


def test_session_serialization():
    recorder = SessionRecorder()
    recorder.start()

    recorder.record(make_event())

    payload = recorder.session.as_dict()

    assert payload["session_id"]
    assert len(payload["events"]) == 1


def test_summary_serialization():
    recorder = SessionRecorder()
    recorder.start()

    summary = recorder.stop()

    payload = summary.as_dict()

    assert payload["session_id"]
    assert payload["commands"] == 0
