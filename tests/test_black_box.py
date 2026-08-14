import json

import pytest

from truepanel.history.black_box import (
    REDACTED,
    BlackBoxFrame,
    BlackBoxRecorder,
    sanitize_black_box_value,
)


def test_sanitizer_redacts_sensitive_keys_and_embedded_identifiers():
    sanitized = sanitize_black_box_value(
        {
            "hostname": "BattleStation",
            "drive_serial": "secret-drive-id",
            "nested": {
                "mac_address": "aa:bb:cc:dd:ee:ff",
                "safe": 42,
            },
            "lcd": "NAS 192.168.0.108 aa:bb:cc:dd:ee:ff",
            "uuid_text": "pool 123e4567-e89b-12d3-a456-426614174000",
        }
    )

    assert sanitized["hostname"] == REDACTED
    assert sanitized["drive_serial"] == REDACTED
    assert sanitized["nested"]["mac_address"] == REDACTED
    assert sanitized["nested"]["safe"] == 42
    assert "192.168.0.108" not in sanitized["lcd"]
    assert "aa:bb:cc:dd:ee:ff" not in sanitized["lcd"]
    assert "123e4567-e89b-12d3-a456-426614174000" not in sanitized["uuid_text"]


def test_capture_sanitizes_all_black_box_sections():
    frame = BlackBoxFrame.capture(
        captured_at=123.5,
        sequence=7,
        telemetry={"cpu_percent": 12.5, "hostname": "nas"},
        lcd={"line1": "IP 10.0.0.5", "page": "show_ip"},
        fan={"rpm": [1500, 1450]},
        storage={"pool_health": "ONLINE", "wwn": "secret"},
        alerts=[{"severity": "warning", "message": "host 10.0.0.5"}],
        buttons={"button_reports": 3},
        mission_control={"healthy": True, "username": "admin"},
    )

    assert frame.telemetry == {
        "cpu_percent": 12.5,
        "hostname": REDACTED,
    }
    assert frame.lcd["line1"] == f"IP {REDACTED}"
    assert frame.storage["wwn"] == REDACTED
    assert frame.alerts[0]["message"] == f"host {REDACTED}"
    assert frame.mission_control["username"] == REDACTED
    assert frame.privacy == "sanitized"
    assert frame.schema_version == 1


def test_recorder_round_trip_is_compact_and_replayable(tmp_path):
    path = tmp_path / "black-box.jsonl"
    recorder = BlackBoxRecorder(path)
    frame = BlackBoxFrame.capture(
        captured_at=100.0,
        sequence=1,
        telemetry={"cpu_percent": 20.0},
        lcd={"line1": "TruePanel", "line2": "Mission Ready"},
    )

    written = recorder.append(frame)

    raw = path.read_text(encoding="utf-8")
    assert written == len(raw.rstrip("\n").encode("utf-8"))
    assert raw.count("\n") == 1
    assert ": " not in raw

    payload = json.loads(raw)
    assert payload["privacy"] == "sanitized"
    assert list(recorder.replay()) == [frame]


def test_replay_rejects_unsanitized_or_unknown_schema(tmp_path):
    path = tmp_path / "black-box.jsonl"
    recorder = BlackBoxRecorder(path)

    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "privacy": "raw",
                "captured_at": 1,
                "sequence": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="line 1"):
        list(recorder.replay())

    path.write_text(
        json.dumps(
            {
                "schema_version": 99,
                "privacy": "sanitized",
                "captured_at": 1,
                "sequence": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="schema version"):
        list(recorder.replay())


def test_recorder_rejects_oversized_frames(tmp_path):
    recorder = BlackBoxRecorder(
        tmp_path / "black-box.jsonl",
        max_frame_bytes=1024,
    )
    frame = BlackBoxFrame.capture(
        captured_at=1.0,
        sequence=1,
        telemetry={"blob": "x" * 2000},
    )

    with pytest.raises(ValueError, match="exceeds maximum size"):
        recorder.append(frame)
