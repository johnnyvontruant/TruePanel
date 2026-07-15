from truepanel.mission_control.constants import Priority
from truepanel.mission_control.display_manager import (
    DisplayManager,
)


class FakeMission:
    pass


class FakeAlertManager:
    pass


class EmptyRegistry:
    dashboard_pages = []


def make_manager():
    return DisplayManager(
        FakeMission(),
        FakeAlertManager(),
        registry=EmptyRegistry(),
    )


def test_activity_dashboard_renders_history():
    manager = make_manager()

    manager._dashboard_activity(
        {
            "zfs_activity": {
                "read_bytes_per_sec": 100,
                "write_bytes_per_sec": 0,
            }
        }
    )

    frame = manager._dashboard_activity(
        {
            "zfs_activity": {
                "read_bytes_per_sec": 50,
                "write_bytes_per_sec": 0,
            }
        }
    )

    assert frame.lines[0].strip() == "R   50B W    0B"
    assert frame.lines[1].startswith("ACT ")
    assert len(frame.lines[1]) == 16
    assert manager.activity_history == [
        100.0,
        50.0,
    ]


def test_activity_dashboard_idle_keeps_sparkline():
    manager = make_manager()

    frame = manager._dashboard_activity(
        {
            "zfs_activity": {},
        }
    )

    assert frame.lines[0].strip() == "ZFS POOL IDLE"
    assert frame.lines[1].startswith("ACT ")
    assert frame.priority is Priority.INFO


def test_activity_history_is_limited():
    manager = make_manager()

    for value in range(20):
        manager._dashboard_activity(
            {
                "zfs_activity": {
                    "read_bytes_per_sec": value,
                }
            }
        )

    assert manager.activity_history == [
        float(value)
        for value in range(4, 20)
    ]
