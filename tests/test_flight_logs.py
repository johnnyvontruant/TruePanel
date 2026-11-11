"""Read-only Flight Log query tests."""
import pytest

from truepanel.flight_logs import recent


def test_filter_recent(tmp_path):
    path = tmp_path / "flight.log"
    path.write_text(
        "2026-11-02T20:00:00+00:00 | INFO     | SYSTEM   | started\n"
        "2026-11-02T20:01:00+00:00 | ALERT    | BUZZER   | long\n"
        "2026-11-02T20:02:00+00:00 | WARNING  | STORAGE  | bay 3\n"
        "2026-11-02T20:03:00+00:00 | ALERT    | BUZZER   | short\n",
        encoding="utf-8",
    )
    assert len(recent(path, limit=2)) == 2
    assert len(recent(path, category="buzzer")) == 2
    assert len(recent(path, severity="warning")) == 1
    assert recent(path, category="network") == []


def test_missing_file_and_bounded_query(tmp_path):
    assert recent(tmp_path / "missing.log") == []
    with pytest.raises(ValueError):
        recent(tmp_path / "missing.log", limit=1001)
