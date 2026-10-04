from __future__ import annotations

import pytest

from truepanel.cargo.copy_button import (
    COPY_BUTTON_BANK,
    COPY_BUTTON_BIT,
    LoadmasterCopyButtonGate,
    LoadmasterPhysicalPreflight,
)


class Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class Level:
    def __init__(self, value: int = 1) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value


def ready_preflight(clock: Clock, **overrides) -> LoadmasterPhysicalPreflight:
    payload = {
        "cartridge_id": "movies-num-d",
        "cartridge_uuid": "6989-100A",
        "device_serial": "2532EA8D3ED1",
        "plan_state": "READY",
        "backup_files": 1,
        "backup_bytes": 12_059_382_205,
        "baseline_verified": True,
        "identity_verified": True,
        "backlog_verified": True,
        "plan_digest": "abc123",
        "generated_at_monotonic": clock(),
    }
    payload.update(overrides)
    return LoadmasterPhysicalPreflight(**payload)


def settle(
    gate: LoadmasterCopyButtonGate,
    clock: Clock,
    *,
    seconds: float = 0.08,
):
    assert gate.poll() is None
    clock.advance(seconds)
    return gate.poll()


def test_copy_button_mapping_is_verified_gpio75() -> None:
    assert COPY_BUTTON_BANK == 7
    assert COPY_BUTTON_BIT == 5


@pytest.mark.parametrize(
    "field,value",
    [
        ("plan_state", "HOLD"),
        ("backup_files", 0),
        ("backup_bytes", 0),
        ("baseline_verified", False),
        ("identity_verified", False),
        ("backlog_verified", False),
        ("plan_digest", ""),
        ("cartridge_uuid", ""),
        ("device_serial", ""),
    ],
)
def test_arm_rejects_incomplete_preflight(
    field: str,
    value: object,
) -> None:
    clock = Clock()
    level = Level()
    gate = LoadmasterCopyButtonGate(read_level=level, clock=clock)
    with pytest.raises(ValueError, match="not READY"):
        gate.arm(ready_preflight(clock, **{field: value}))


def test_arm_rejects_stale_preflight() -> None:
    clock = Clock()
    level = Level()
    gate = LoadmasterCopyButtonGate(
        read_level=level,
        clock=clock,
        confirmation_window_seconds=30.0,
    )
    stale = ready_preflight(
        clock,
        generated_at_monotonic=clock() - 31.0,
    )
    with pytest.raises(ValueError, match="stale"):
        gate.arm(stale)


def test_press_does_nothing_when_not_armed() -> None:
    clock = Clock()
    level = Level(1)
    gate = LoadmasterCopyButtonGate(read_level=level, clock=clock)

    settle(gate, clock)
    level.value = 0
    assert settle(gate, clock) is None


def test_active_low_press_confirms_once_after_debounce() -> None:
    clock = Clock()
    level = Level(1)
    gate = LoadmasterCopyButtonGate(read_level=level, clock=clock)
    gate.arm(ready_preflight(clock))

    settle(gate, clock)
    level.value = 0
    confirmation = settle(gate, clock)

    assert confirmation is not None
    assert confirmation.cartridge_id == "movies-num-d"
    assert confirmation.cartridge_uuid == "6989-100A"
    assert confirmation.device_serial == "2532EA8D3ED1"
    assert confirmation.plan_digest == "abc123"
    assert confirmation.source == "fintek_gpio75"
    assert confirmation.active_low is True

    clock.advance(1.0)
    assert gate.poll() is None


def test_release_and_second_press_cannot_reuse_same_plan_digest() -> None:
    clock = Clock()
    level = Level(1)
    gate = LoadmasterCopyButtonGate(read_level=level, clock=clock)
    gate.arm(ready_preflight(clock))

    settle(gate, clock)
    level.value = 0
    assert settle(gate, clock) is not None

    level.value = 1
    assert settle(gate, clock) is None

    clock.advance(1.0)
    level.value = 0
    assert settle(gate, clock) is None


def test_consumed_plan_digest_cannot_be_rearmed() -> None:
    clock = Clock()
    level = Level(1)
    gate = LoadmasterCopyButtonGate(read_level=level, clock=clock)
    first = ready_preflight(clock)
    gate.arm(first)

    settle(gate, clock)
    level.value = 0
    assert settle(gate, clock) is not None
    level.value = 1
    settle(gate, clock)

    clock.advance(1.0)
    with pytest.raises(ValueError, match="already consumed"):
        gate.arm(
            ready_preflight(
                clock,
                generated_at_monotonic=clock(),
            )
        )


def test_new_ready_plan_can_be_armed_after_first_is_consumed() -> None:
    clock = Clock()
    level = Level(1)
    gate = LoadmasterCopyButtonGate(read_level=level, clock=clock)
    gate.arm(ready_preflight(clock))

    settle(gate, clock)
    level.value = 0
    assert settle(gate, clock) is not None
    level.value = 1
    settle(gate, clock)

    clock.advance(1.0)
    gate.arm(
        ready_preflight(
            clock,
            plan_digest="def456",
            generated_at_monotonic=clock(),
        )
    )
    level.value = 0
    second = settle(gate, clock)

    assert second is not None
    assert second.plan_digest == "def456"


def test_expired_arm_fails_closed() -> None:
    clock = Clock()
    level = Level(1)
    gate = LoadmasterCopyButtonGate(
        read_level=level,
        clock=clock,
        confirmation_window_seconds=1.0,
    )
    gate.arm(ready_preflight(clock))

    settle(gate, clock)
    clock.advance(1.1)
    level.value = 0
    assert settle(gate, clock) is None
    assert gate.armed_snapshot()["armed"] is False


def test_public_confirmation_hides_device_serial() -> None:
    clock = Clock()
    level = Level(1)
    gate = LoadmasterCopyButtonGate(read_level=level, clock=clock)
    gate.arm(ready_preflight(clock))

    settle(gate, clock)
    level.value = 0
    confirmation = settle(gate, clock)

    assert confirmation is not None
    payload = confirmation.public_dict()
    assert "device_serial" not in payload
    assert payload["source"] == "fintek_gpio75"