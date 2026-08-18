import json
import math

import pytest

from truepanel.history.black_box import (
    MAX_BLACK_BOX_FRAME_BYTES,
    MAX_BLACK_BOX_REPLAY_BYTES,
    MAX_BLACK_BOX_REPLAY_FRAMES,
    REDACTED,
    BlackBoxFrame,
    BlackBoxRecorder,
    BlackBoxReplay,
    sanitize_black_box_value,
)


def encoded_frame(sequence=1):
    frame = BlackBoxFrame.capture(
        captured_at=float(sequence),
        sequence=sequence,
    )
    return json.dumps(
        frame.as_dict(),
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


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
    assert (
        "123e4567-e89b-12d3-a456-426614174000"
        not in sanitized["uuid_text"]
    )


@pytest.mark.parametrize(
    "key",
    ["api_key", "access_key", "authorization", "cookie", "client_secret", "session"],
)
def test_sanitizer_redacts_common_credential_keys(key):
    assert sanitize_black_box_value({key: "private"})[key] == REDACTED


def test_capture_sanitizes_all_black_box_sections():
    frame = BlackBoxFrame.capture(
        captured_at=123.5,
        sequence=7,
        telemetry={"cpu_percent": 12.5, "hostname": "nas"},
        lcd={"line1": "IP 10.0.0.5", "page": "show_ip"},
        fan={"rpm": [1500, 1450]},
        storage={"pool_health": "ONLINE", "wwn": "secret"},
        alerts=[
            {
                "severity": "warning",
                "message": "host 10.0.0.5",
            }
        ],
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
        lcd={
            "line1": "TruePanel",
            "line2": "Mission Ready",
        },
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


def test_append_resanitizes_directly_constructed_and_mutated_frames(tmp_path):
    recorder = BlackBoxRecorder(tmp_path / "black-box.jsonl")
    frame = BlackBoxFrame(
        captured_at=1,
        sequence=1,
        telemetry={"hostname": "private-nas", "note": "IP 192.168.1.9"},
    )
    frame.telemetry["drive_serial"] = "private-serial"

    recorder.append(frame)
    payload = json.loads(recorder.path.read_text())
    assert payload["telemetry"]["hostname"] == REDACTED
    assert payload["telemetry"]["drive_serial"] == REDACTED
    assert "192.168.1.9" not in payload["telemetry"]["note"]


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_capture_rejects_non_finite_timestamps(value):
    with pytest.raises(ValueError, match="must be finite"):
        BlackBoxFrame.capture(captured_at=value, sequence=1)


def test_capture_rejects_boolean_sequence():
    with pytest.raises(ValueError, match="must be an integer"):
        BlackBoxFrame.capture(captured_at=1, sequence=True)


def test_recorder_rejects_non_finite_nested_numbers(tmp_path):
    recorder = BlackBoxRecorder(tmp_path / "black-box.jsonl")
    frame = BlackBoxFrame.capture(
        captured_at=1,
        sequence=1,
        telemetry={"temperature": math.nan},
    )
    with pytest.raises(ValueError):
        recorder.append(frame)


def test_replay_enforces_imported_frame_size_limit(tmp_path):
    recorder = BlackBoxRecorder(tmp_path / "black-box.jsonl", max_frame_bytes=1024)
    recorder.path.write_text("{" + '"padding":"' + ("x" * 2000) + '"}')
    with pytest.raises(ValueError, match="exceeds maximum size"):
        list(recorder.replay())


def test_replay_frame_limit_is_enforced_before_materialization(tmp_path):
    path = tmp_path / "black-box.jsonl"
    path.write_bytes(b"\n".join(encoded_frame(index) for index in range(1, 4)))
    recorder = BlackBoxRecorder(path, max_replay_frames=2)

    iterator = iter(recorder.replay())
    assert next(iterator).sequence == 1
    assert next(iterator).sequence == 2
    with pytest.raises(ValueError, match="frame limit exceeded: 3 > 2"):
        next(iterator)


def test_replay_accepts_exact_frame_and_byte_limits(tmp_path):
    path = tmp_path / "black-box.jsonl"
    raw = encoded_frame(1) + b"\r\n" + encoded_frame(2)
    path.write_bytes(raw)

    replay = BlackBoxRecorder(
        path,
        max_replay_frames=2,
        max_replay_bytes=len(raw),
    ).load_replay()

    assert [frame.sequence for frame in replay.frames] == [1, 2]


def test_replay_rejects_one_byte_over_total_limit(tmp_path):
    path = tmp_path / "black-box.jsonl"
    raw = encoded_frame() + b"\n"
    path.write_bytes(raw)

    with pytest.raises(ValueError, match="byte limit exceeded"):
        BlackBoxRecorder(
            path,
            max_replay_bytes=len(raw) - 1,
        ).load_replay()


def test_replay_total_limit_counts_blank_lines(tmp_path):
    path = tmp_path / "black-box.jsonl"
    raw = b" " * 32 + b"\n" + encoded_frame()
    path.write_bytes(raw)

    with pytest.raises(ValueError, match="byte limit exceeded"):
        BlackBoxRecorder(
            path,
            max_replay_bytes=len(raw) - 1,
        ).load_replay()


def test_replay_streams_oversized_blank_lines_without_counting_frames(tmp_path):
    path = tmp_path / "black-box.jsonl"
    path.write_bytes(b" " * 2048 + b"\n" + encoded_frame())

    replay = BlackBoxRecorder(
        path,
        max_frame_bytes=1024,
    ).load_replay()

    assert [frame.sequence for frame in replay.frames] == [1]


def test_replay_wraps_invalid_utf8_with_physical_line_number(tmp_path):
    path = tmp_path / "black-box.jsonl"
    path.write_bytes(b"\n\xff\n")

    with pytest.raises(ValueError, match="frame at line 2"):
        BlackBoxRecorder(path).load_replay()


def test_replay_accepts_final_frame_without_line_terminator(tmp_path):
    path = tmp_path / "black-box.jsonl"
    path.write_bytes(encoded_frame())

    assert BlackBoxRecorder(path).load_replay().frames[0].sequence == 1


@pytest.mark.parametrize(
    ("keyword", "value"),
    (
        ("max_frame_bytes", MAX_BLACK_BOX_FRAME_BYTES + 1),
        ("max_replay_frames", MAX_BLACK_BOX_REPLAY_FRAMES + 1),
        ("max_replay_bytes", MAX_BLACK_BOX_REPLAY_BYTES + 1),
    ),
)
def test_replay_limits_cannot_exceed_authoritative_ceiling(
    tmp_path,
    keyword,
    value,
):
    with pytest.raises(ValueError, match="limit must be between"):
        BlackBoxRecorder(tmp_path / "black-box.jsonl", **{keyword: value})


def replay_fixture():
    return [
        BlackBoxFrame.capture(
            captured_at=100.0,
            sequence=10,
            lcd={
                "page": "show_truenas",
                "line1": "TrueNAS",
            },
        ),
        BlackBoxFrame.capture(
            captured_at=105.0,
            sequence=11,
            lcd={
                "page": "show_pool_health",
                "line1": "Pools ONLINE",
            },
        ),
        BlackBoxFrame.capture(
            captured_at=112.5,
            sequence=13,
            lcd={
                "page": "show_fan_rpm",
                "line1": "Fan 1 1500 RPM",
            },
        ),
    ]


def test_replay_supports_deterministic_time_and_sequence_queries():
    replay = BlackBoxReplay(replay_fixture())

    assert len(replay) == 3
    assert replay.duration_seconds == 12.5
    assert replay.at_sequence(11).lcd["page"] == "show_pool_health"
    assert replay.at_sequence(12) is None
    assert replay.at_or_before(99.9) is None
    assert replay.at_or_before(109).sequence == 11
    assert [
        frame.sequence
        for frame in replay.between(101, 112.5)
    ] == [11, 13]

    with pytest.raises(ValueError, match="end precedes start"):
        replay.between(10, 9)


def test_replay_rejects_ambiguous_or_backward_recordings():
    frames = replay_fixture()

    with pytest.raises(ValueError, match="sequences must increase"):
        BlackBoxReplay([frames[0], frames[0]])

    backward = BlackBoxFrame.capture(
        captured_at=99.0,
        sequence=14,
    )
    with pytest.raises(
        ValueError,
        match="timestamps must not move backward",
    ):
        BlackBoxReplay([frames[-1], backward])


def test_replay_cursor_steps_seeks_and_never_touches_runtime():
    replay = BlackBoxReplay(replay_fixture())
    cursor = replay.cursor()

    assert cursor.current.sequence == 10
    assert cursor.step().sequence == 11
    assert cursor.step(50).sequence == 13
    assert cursor.step(-50).sequence == 10
    assert cursor.seek_sequence(13).lcd["page"] == "show_fan_rpm"
    assert cursor.seek_sequence(999) is None
    assert cursor.current.sequence == 13
    assert cursor.seek_time(106).sequence == 11
    assert [
        frame.sequence
        for frame in cursor.remaining()
    ] == [11, 13]


def test_recorder_load_replay_validates_recording_order(tmp_path):
    recorder = BlackBoxRecorder(tmp_path / "black-box.jsonl")

    for frame in replay_fixture():
        recorder.append(frame)

    replay = recorder.load_replay()

    assert [
        frame.sequence
        for frame in replay.frames
    ] == [10, 11, 13]
