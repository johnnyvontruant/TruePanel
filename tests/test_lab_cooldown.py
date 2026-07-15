import pytest

from truepanel.lab.cooldown import CooldownTracker


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def test_new_key_is_ready():
    tracker = CooldownTracker(
        cooldown_seconds=5,
    )

    assert tracker.ready("opcode")


def test_record_starts_cooldown():
    clock = FakeClock()
    tracker = CooldownTracker(
        cooldown_seconds=5,
        clock=clock,
    )

    tracker.record("opcode")

    assert not tracker.ready("opcode")
    assert tracker.remaining("opcode") == pytest.approx(
        5.0
    )


def test_cooldown_expires():
    clock = FakeClock()
    tracker = CooldownTracker(
        cooldown_seconds=5,
        clock=clock,
    )

    tracker.record("opcode")
    clock.advance(5)

    assert tracker.ready("opcode")
    assert tracker.remaining("opcode") == 0.0


def test_keys_are_independent():
    clock = FakeClock()
    tracker = CooldownTracker(
        cooldown_seconds=5,
        clock=clock,
    )

    tracker.record("board")

    assert not tracker.ready("board")
    assert tracker.ready("version")


def test_clear_single_key():
    clock = FakeClock()
    tracker = CooldownTracker(
        cooldown_seconds=5,
        clock=clock,
    )

    tracker.record("board")
    tracker.clear("board")

    assert tracker.ready("board")


def test_negative_cooldown_rejected():
    with pytest.raises(ValueError):
        CooldownTracker(
            cooldown_seconds=-1,
        )
