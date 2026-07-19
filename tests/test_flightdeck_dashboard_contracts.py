from truepanel.mission_control.constants import Priority
from truepanel.mission_control.display_manager import (
    DisplayManager,
    DisplayMode,
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


def assert_dashboard_frame(frame):
    assert frame.mode is DisplayMode.DASHBOARD
    assert frame.interrupt is False
    assert len(frame.lines) == 2
    assert all(len(line) == 16 for line in frame.lines)


def test_performance_dashboard_contract():
    manager = make_manager()
    frame = manager._dashboard_performance(
        {
            "cpu_percent": 50,
            "ram_percent": 75,
        }
    )

    assert_dashboard_frame(frame)
    rendered = " ".join(frame.lines)
    assert "50%" in rendered
    assert "75%" in rendered
    assert frame.priority is Priority.INFO


def test_performance_dashboard_warning_contract():
    manager = make_manager()
    frame = manager._dashboard_performance(
        {
            "cpu_percent": 90,
            "ram_percent": 20,
        }
    )

    assert_dashboard_frame(frame)
    assert frame.priority is Priority.WARNING


def test_capacity_dashboard_contract():
    manager = make_manager()
    frame = manager._dashboard_capacity(
        {
            "pools": [
                {"name": "tank", "capacity": "82%"},
                {"name": "backup", "capacity": "40%"},
            ]
        }
    )

    assert_dashboard_frame(frame)
    assert "82%" in " ".join(frame.lines)
    assert frame.priority is Priority.INFO


def test_capacity_dashboard_critical_contract():
    manager = make_manager()
    frame = manager._dashboard_capacity(
        {
            "pools": [
                {"name": "tank", "capacity": "95%"},
            ]
        }
    )

    assert_dashboard_frame(frame)
    assert frame.priority is Priority.CRITICAL


def test_capacity_dashboard_no_data_contract():
    manager = make_manager()
    frame = manager._dashboard_capacity({"pools": []})

    assert_dashboard_frame(frame)
    assert "No Pool Data" in " ".join(frame.lines)
    assert frame.priority is Priority.INFO


def test_thermal_dashboard_contract():
    manager = make_manager()
    frame = manager._dashboard_thermal(
        {
            "temps": [
                {"drive": "sda", "temp": 38},
                {"drive": "sdb", "temp": 50},
            ]
        }
    )

    assert_dashboard_frame(frame)
    assert "50C" in " ".join(frame.lines)
    assert frame.priority is Priority.WARNING


def test_thermal_dashboard_no_data_contract():
    manager = make_manager()
    frame = manager._dashboard_thermal({"temps": []})

    assert_dashboard_frame(frame)
    assert "No Temp Data" in " ".join(frame.lines)
    assert frame.priority is Priority.INFO


def test_activity_dashboard_contract():
    manager = make_manager()
    frame = manager._dashboard_activity(
        {
            "zfs_activity": {
                "read_bytes_per_sec": 2048,
                "write_bytes_per_sec": 1024,
            }
        }
    )

    assert_dashboard_frame(frame)


def test_network_dashboard_contract():
    manager = make_manager()
    frame = manager._dashboard_network(
        {
            "network": {
                "download_bytes_per_sec": 2048,
                "upload_bytes_per_sec": 1024,
            }
        }
    )

    assert_dashboard_frame(frame)
