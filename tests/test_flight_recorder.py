"""Flight Recorder basic contract tests."""
from pathlib import Path

from truepanel.flight_recorder import record


def test_flight_record_creates_file(tmp_path):
    path = tmp_path / "logs" / "flight.log"
    assert record("storage", "warning", "Bay 3 fault", path=path)
    line = path.read_text(encoding="utf-8")
    assert "WARNING" in line and "STORAGE" in line
    assert "Bay 3 fault" in line


def test_multiline_message_cannot_forge_entries(tmp_path):
    path = tmp_path / "flight.log"
    assert record("buzzer", "alert", "beep\nforged", path=path)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_fails_open_when_path_unwritable(tmp_path):
    assert not record("system", "info", "test", path=tmp_path)
