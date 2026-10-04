from __future__ import annotations

import time

from truepanel.cargo.copy_button import LoadmasterPhysicalPreflight
from truepanel.host.loadmaster_copy_button import (
    LoadmasterCopyButtonService,
)


class Reader:
    def __init__(self) -> None:
        self.level = 1
        self.closed = False

    def read_level(self) -> int:
        return self.level

    def close(self) -> None:
        self.closed = True


def preflight() -> LoadmasterPhysicalPreflight:
    return LoadmasterPhysicalPreflight(
        cartridge_id="movies-num-d",
        cartridge_uuid="6989-100A",
        device_serial="2532EA8D3ED1",
        plan_state="READY",
        backup_files=1,
        backup_bytes=12_059_382_205,
        baseline_verified=True,
        identity_verified=True,
        backlog_verified=True,
        plan_digest="plan-a",
        generated_at_monotonic=time.monotonic(),
    )


def wait_for(predicate, timeout: float = 1.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.005)
    return False


def test_service_accepts_one_armed_press_and_disarms() -> None:
    reader = Reader()
    confirmations = []
    events = []
    service = LoadmasterCopyButtonService(
        reader=reader,
        on_confirmation=confirmations.append,
        event_recorder=events.append,
        poll_seconds=0.005,
    )
    service.arm(preflight())
    service.start()

    try:
        time.sleep(0.02)
        reader.level = 0
        assert wait_for(lambda: len(confirmations) == 1)
        assert confirmations[0].plan_digest == "plan-a"
        assert service.snapshot()["armed"] is False
        assert any(
            item.get("event") == "confirmed"
            for item in events
        )
    finally:
        service.stop()

    assert reader.closed is True


def test_unarmed_press_never_confirms() -> None:
    reader = Reader()
    confirmations = []
    service = LoadmasterCopyButtonService(
        reader=reader,
        on_confirmation=confirmations.append,
        poll_seconds=0.005,
    )
    service.start()

    try:
        reader.level = 0
        time.sleep(0.12)
        assert confirmations == []
        assert service.snapshot()["armed"] is False
    finally:
        service.stop()


def test_reader_error_fails_closed_and_stops() -> None:
    class BrokenReader(Reader):
        def read_level(self) -> int:
            raise OSError("reader unavailable")

    reader = BrokenReader()
    events = []
    service = LoadmasterCopyButtonService(
        reader=reader,
        event_recorder=events.append,
        poll_seconds=0.005,
    )
    service.arm(preflight())
    service.start()

    try:
        assert wait_for(
            lambda: service.snapshot()["last_error"] is not None
        )
        snapshot = service.snapshot()
        assert snapshot["armed"] is False
        assert "reader unavailable" in str(snapshot["last_error"])
        assert any(
            item.get("event") == "reader_error"
            for item in events
        )
    finally:
        service.stop()


def test_service_start_and_stop_are_idempotent() -> None:
    reader = Reader()
    service = LoadmasterCopyButtonService(
        reader=reader,
        poll_seconds=0.005,
    )

    service.start()
    service.start()
    assert service.started is True

    service.stop()
    service.stop()
    assert service.started is False
    assert reader.closed is True