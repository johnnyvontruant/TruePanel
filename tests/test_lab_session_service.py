from datetime import UTC, datetime

import pytest

from truepanel.lab.commands import LabResult
from truepanel.lab.session import SessionEvent
from truepanel.lab.session_service import SessionService


def make_event():
    return SessionEvent(
        timestamp=datetime.now(UTC),
        command="discover",
        success=True,
        duration_ms=42.0,
        capture_path="discover.log",
    )


def make_result():
    return LabResult(
        command="discover",
        success=True,
        capture_path="discover.log",
        data={
            "board_id": "0x007D",
        },
    )


def test_start_session():
    service = SessionService()

    session = service.start_session()

    assert session.active
    assert service.current_session() is session


def test_stop_session_returns_summary():
    service = SessionService()

    service.start_session()

    summary = service.stop_session()

    assert summary.commands == 0
    assert service.current_summary() is summary


def test_record_event():
    service = SessionService()

    service.start_session()

    service.record_event(make_event())

    assert len(service.current_session().events) == 1


def test_record_lab_result():
    service = SessionService()

    service.start_session()

    service.record_lab_result(
        make_result(),
        duration_ms=123.4,
    )

    event = service.current_session().events[0]

    assert event.command == "discover"
    assert event.success is True
    assert event.capture_path == "discover.log"
    assert event.duration_ms == pytest.approx(123.4)


def test_lab_result_metadata_preserved():
    service = SessionService()

    service.start_session()

    service.record_lab_result(make_result())

    event = service.current_session().events[0]

    assert event.metadata["board_id"] == "0x007D"


def test_record_without_session():
    service = SessionService()

    with pytest.raises(RuntimeError):
        service.record_event(make_event())


def test_record_lab_result_without_session():
    service = SessionService()

    with pytest.raises(RuntimeError):
        service.record_lab_result(make_result())


def test_multiple_results():
    service = SessionService()

    service.start_session()

    service.record_lab_result(make_result())
    service.record_lab_result(make_result())

    summary = service.stop_session()

    assert summary.commands == 2
    assert summary.successes == 2
    assert summary.failures == 0
