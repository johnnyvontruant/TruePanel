from __future__ import annotations

import pytest

from truepanel.loadmaster.lcd import enter_ejects, idle_page, pages, size, takeover

STATES = [
    "CHECKING",
    "READY",
    "CONFIRM",
    "CLEAR",
    "COPYING",
    "DONE",
    "PARTIAL",
    "FAILED",
    "STOPPED",
    "HOLD",
    "NEW_DRIVE",
    "EJECTED",
]


def status(state, **extra):
    base = {
        "available": True,
        "state": state,
        "state_since": 1000.0,
        "message": "Something changed since the plan was shown; check it and start again.",
        "drive": {"name": "Movies E-I"},
        "plan": {
            "summary": {
                "to_usb_files": 3,
                "to_usb_bytes": 12_400_000_000,
                "to_nas_files": 1,
                "to_nas_bytes": 4_200_000_000,
                "delete_usb_files": 2,
                "retire_nas_files": 0,
            }
        },
        "progress": {
            "done_bytes": 50,
            "total_bytes": 100,
            "done_files": 0,
            "total_files": 2,
            "current": "Inception (2010)/Inception (2010) Bluray-2160p.mkv",
        },
        "last_run": {
            "summary": {
                "to_usb_files": 3,
                "to_nas_files": 1,
                "copied_bytes": 16_600_000_000,
            }
        },
        "safe_to_remove": True,
    }
    base.update(extra)
    return base


@pytest.mark.parametrize("state", STATES)
def test_every_page_fits(state):
    result = pages(status(state))
    assert result
    for page in result:
        assert len(page) == 2
        assert all(len(line) <= 16 for line in page), page


def test_ready_screens():
    result = pages(status("READY"))
    assert result[0] == ["MOVIES E-I READY", "Press COPY"]
    assert result[1] == ["To USB   3 12.4G", "To NAS   1  4.2G"]
    assert result[2] == ["Remove 2 old", "files on USB"]


def test_copying_shows_progress():
    result = pages(status("COPYING"))
    assert result[0][0] == "MOVIES E-I  50%"
    assert result[1][0] == "File 1/2"
    assert result[2][1] == "Do not unplug"


def test_done_and_failure_screens():
    assert pages(status("DONE"))[0] == ["MOVIES E-I DONE", "Safe to remove"]
    assert pages(status("DONE"))[1] == ["Copied 4 files", "16.6G"]
    assert pages(status("FAILED", safe_to_remove=False))[0][1] == "Do not unplug"


def test_takeover_and_enter():
    assert takeover(status("READY"), 5000)
    assert not takeover(status("IDLE"), 5000)
    assert takeover(status("CLEAR"), 1030) and not takeover(status("CLEAR"), 1100)
    assert not takeover({"available": False, "state": "READY"}, 0)
    assert enter_ejects(status("READY")) and enter_ejects(status("HOLD"))
    assert not enter_ejects(status("COPYING")) and not enter_ejects(status("DONE"))


def test_idle_page():
    drives = [{"name": "TV A-M", "pending_files": 7, "pending_bytes": 14_200_000_000}]
    assert idle_page(status("IDLE", drives=drives)) == ["Next: TV A-M", "7 new 14.2G"]
    assert idle_page(status("IDLE", drives=[])) == ["Loadmaster", "All drives synced"]
    assert idle_page(None) == ["Loadmaster", "Offline"]


def test_size():
    assert [
        size(950_000_000),
        size(12_400_000_000),
        size(2_100_000_000_000),
        size(0),
    ] == ["950M", "12.4G", "2.1T", "0B"]
