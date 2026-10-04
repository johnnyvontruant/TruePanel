from __future__ import annotations

import pytest

from truepanel.host.factory import (
    build_loadmaster_copy_button_service,
)


class Reader:
    def __init__(self) -> None:
        self.level = 1
        self.closed = False

    def read_level(self) -> int:
        return self.level

    def close(self) -> None:
        self.closed = True


def config(**physical_overrides):
    physical = {
        "enabled": True,
        "source": "fintek_gpio",
        "bank": 7,
        "bit": 5,
        "active_low": True,
        "debounce_ms": 75,
        "rearm_ms": 750,
        "confirmation_window_seconds": 30,
    }
    physical.update(physical_overrides)
    return {
        "mission_control": {
            "cargo_bay": {
                "loadmaster": {
                    "physical_confirmation": physical,
                }
            }
        }
    }


def test_disabled_configuration_builds_no_service() -> None:
    reader_calls = []

    service = build_loadmaster_copy_button_service(
        config=config(enabled=False),
        reader_factory=lambda: reader_calls.append(True),
    )

    assert service is None
    assert reader_calls == []


def test_verified_configuration_builds_service() -> None:
    reader = Reader()

    service = build_loadmaster_copy_button_service(
        config=config(),
        reader_factory=lambda: reader,
    )

    assert service is not None
    assert service.reader is reader
    assert service.gate.active_low is True
    assert service.gate.debounce_seconds == pytest.approx(0.075)
    assert service.gate.rearm_seconds == pytest.approx(0.750)
    assert (
        service.gate.confirmation_window_seconds
        == pytest.approx(30.0)
    )


@pytest.mark.parametrize(
    "overrides,match",
    [
        ({"source": "other"}, "unsupported"),
        ({"bank": 6}, "bank"),
        ({"bit": 4}, "bit"),
        ({"active_low": False}, "active-low"),
    ],
)
def test_unverified_hardware_mapping_fails_closed(
    overrides,
    match,
) -> None:
    reader_calls = []

    with pytest.raises(ValueError, match=match):
        build_loadmaster_copy_button_service(
            config=config(**overrides),
            reader_factory=lambda: reader_calls.append(True),
        )

    assert reader_calls == []