from __future__ import annotations

import pytest

from truepanel.pages.loadmaster import (
    LCD_WIDTH,
    format_bytes,
    loadmaster_enter_action,
    loadmaster_pages,
    loadmaster_takeover,
)


def status(state: str, **extra) -> dict:
    payload = {
        "available": True,
        "state": state,
        "reason": None,
        "cartridge": {"label": "Movies E-I", "cartridge_id": "movies-e-i"},
        "plan": {
            "summary": {
                "backup_files": 3,
                "backup_bytes": 12_400_000_000,
                "ingest_files": 1,
                "ingest_bytes": 4_200_000_000,
                "conflicts": 0,
            }
        },
        "progress": None,
        "safe_to_remove": False,
        "last_receipt": None,
        "unregistered": [],
        "state_since": 1000.0,
    }
    payload.update(extra)
    return payload


@pytest.mark.parametrize(
    "state",
    [
        "READY",
        "EXECUTING",
        "HOLD",
        "COMPLETE",
        "PARTIAL",
        "FAILED",
        "CLEAR",
        "EJECTED",
        "UNREGISTERED",
    ],
)
def test_every_line_fits_the_lcd(state):
    payload = status(
        state,
        progress={
            "done_bytes": 5_000_000_000,
            "total_bytes": 16_600_000_000,
            "done_files": 1,
            "total_files": 4,
            "current": "Inception (2010)/Inception (2010) Bluray-1080p.mkv",
        },
        last_receipt={
            "summary": {
                "copied_files": 4,
                "copied_bytes": 16_600_000_000,
                "failed_files": 1,
            }
        },
        unregistered=[{"label": "TV A-M", "uuid": "6989-100A"}],
        reason="PLAN_HOLD: 2 conflict(s)",
    )

    pages = loadmaster_pages(payload)

    assert pages
    for page in pages:
        assert len(page) == 2
        assert all(len(line) <= LCD_WIDTH for line in page)


def test_ready_page_tells_operator_what_moves():
    pages = loadmaster_pages(status("READY"))

    assert pages[0] == ["MOVIES E-I READY", "Press COPY"]
    assert pages[1] == ["To USB   3 12.4G", "To NAS   1  4.2G"]


def test_executing_shows_progress():
    pages = loadmaster_pages(
        status(
            "EXECUTING",
            progress={
                "done_bytes": 50,
                "total_bytes": 100,
                "done_files": 0,
                "total_files": 2,
                "current": "a/b.mkv",
            },
        )
    )

    assert pages[0][0] == "MOVIES E-I  50%"
    assert pages[1][0] == "File 1/2"
    assert pages[2] == ["b.mkv", "Do not unplug"]


def test_complete_only_says_safe_after_unmount():
    assert loadmaster_pages(status("COMPLETE", safe_to_remove=True))[0][1] == (
        "Safe to remove"
    )
    assert loadmaster_pages(status("COMPLETE", safe_to_remove=False))[0][1] == (
        "Do not unplug"
    )


def test_hold_reason_is_humanized():
    pages = loadmaster_pages(status("HOLD", reason="NOT_COMMISSIONED: no inventory"))
    assert pages[0] == ["MOVIES E-I HOLD", "Not commissioned"]


def test_takeover_rules():
    assert loadmaster_takeover(status("READY"), now=5000)
    assert not loadmaster_takeover(status("IDLE"), now=5000)
    assert not loadmaster_takeover({"available": False, "state": "READY"}, now=0)
    assert loadmaster_takeover(status("CLEAR"), now=1030)
    assert not loadmaster_takeover(status("CLEAR"), now=1100)


def test_enter_ejects_only_docked_idle_states():
    assert loadmaster_enter_action(status("READY")) == "eject"
    assert loadmaster_enter_action(status("HOLD")) == "eject"
    assert loadmaster_enter_action(status("EXECUTING")) is None
    assert loadmaster_enter_action(status("COMPLETE")) is None


def test_format_bytes():
    assert format_bytes(950_000_000) == "950M"
    assert format_bytes(12_400_000_000) == "12.4G"
    assert format_bytes(2_100_000_000_000) == "2.1T"
    assert format_bytes(0) == "0B"
