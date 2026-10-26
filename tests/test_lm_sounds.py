from __future__ import annotations

import struct
from datetime import datetime

import pytest

from truepanel.hardware.buzzer import Buzzer
from truepanel.loadmaster.config import LoadmasterConfigError, load_settings
from truepanel.loadmaster.sounds import STATE_TONES, TONES, Sounds, parse_sounds


class Player:
    enabled = True

    def __init__(self):
        self.played = []

    def melody(self, notes):
        self.played.append(notes)
        return True


def at(hour, minute=0):
    return lambda: datetime(2026, 10, 25, hour, minute)


def test_parse_sounds():
    assert parse_sounds(None)["enabled"] is True
    assert parse_sounds(False)["enabled"] is False
    parsed = parse_sounds(
        {"quiet_hours": "22:00-07:30", "tones": {"done": [[1000, 0.1]]}}
    )
    assert parsed["quiet_hours"] == (22 * 60, 7 * 60 + 30)
    assert parsed["tones"] == {"done": [(1000, 0.1)]}
    for bad in (
        "loud",
        {"quiet_hours": "late"},
        {"quiet_hours": "25:00-07:00"},
        {"tones": {"party": [[440, 0.1]]}},
        {"tones": {"done": [[440, 9]]}},
        {"tones": {"done": []}},
    ):
        with pytest.raises(ValueError):
            parse_sounds(bad)


def test_bad_sounds_section_is_a_config_error():
    with pytest.raises(LoadmasterConfigError):
        load_settings(
            {
                "loadmaster": {
                    "enabled": True,
                    "sounds": {"quiet_hours": "late"},
                    "drives": [{"name": "TV A-M", "nas_path": "/n/a"}],
                }
            }
        )


def test_each_state_plays_its_tone_unless_quiet():
    player = Player()
    sounds = Sounds(parse_sounds({"quiet_hours": "22:00-07:00"}), player, now=at(12))
    assert sounds.play("done", wait=True)
    assert player.played == [TONES["done"]]
    for clock in (at(23), at(3), at(6, 59)):  # across midnight
        assert not Sounds(
            sounds_cfg := parse_sounds({"quiet_hours": "22:00-07:00"}),
            player,
            now=clock,
        ).play("done", wait=True)
    assert Sounds(sounds_cfg, player, now=at(7)).play("ready", wait=True)
    daytime = parse_sounds({"quiet_hours": "13:00-14:00"})
    assert not Sounds(daytime, player, now=at(13, 30)).play("ready", wait=True)
    assert set(STATE_TONES.values()) == set(TONES)


def test_tones_are_silent_when_off_or_without_a_buzzer():
    player = Player()
    assert not Sounds(parse_sounds(False), player).play("done", wait=True)
    player.enabled = False
    assert not Sounds(parse_sounds(True), player).play("done", wait=True)
    assert player.played == []


def test_tone_override():
    player = Player()
    Sounds(parse_sounds({"tones": {"done": [[1000, 0.05]]}}), player).play(
        "done", wait=True
    )
    assert player.played == [[(1000, 0.05)]]


def test_buzzer_melody_writes_input_events(tmp_path, monkeypatch):
    device = tmp_path / "event-spkr"
    device.write_bytes(b"")
    monkeypatch.setattr("truepanel.hardware.buzzer.time.sleep", lambda s: None)
    buzzer = Buzzer({"enabled": True, "device": str(device), "cooldown": 30})
    buzzer.last_beep = 10**12  # inside the alert cooldown: tones still play
    assert buzzer.melody([(1047, 0.1), (784, 0.1)])
    size = struct.calcsize("llHHi")
    data = device.read_bytes()
    tones = [
        struct.unpack("llHHi", data[i : i + size])[4] for i in range(0, len(data), size)
    ]
    assert tones == [1047, 0, 784, 0, 0]
    assert not Buzzer({"enabled": False, "device": str(device)}).melody([(440, 0.1)])
