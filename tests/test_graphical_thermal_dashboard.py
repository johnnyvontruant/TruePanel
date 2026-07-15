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


def test_thermal_dashboard_uses_hottest_drive():
    manager = make_manager()

    frame = manager._dashboard_thermal(
        {
            "temps": [
                {
                    "drive": "sda",
                    "temp": 38,
                },
                {
                    "drive": "sdb",
                    "temp": 50,
                },
            ]
        }
    )

    assert frame.lines == [
        "TEMP sdb   50C  ",
        "TMP ###---  50% ",
    ]


def test_thermal_dashboard_healthy_below_fifty():
    manager = make_manager()

    frame = manager._dashboard_thermal(
        {
            "temps": [
                {
                    "drive": "sda",
                    "temp": 49,
                }
            ]
        }
    )

    assert frame.priority is Priority.HEALTHY


def test_thermal_dashboard_warns_at_fifty():
    manager = make_manager()

    frame = manager._dashboard_thermal(
        {
            "temps": [
                {
                    "drive": "sda",
                    "temp": 50,
                }
            ]
        }
    )

    assert frame.priority is Priority.WARNING


def test_thermal_dashboard_critical_at_sixty():
    manager = make_manager()

    frame = manager._dashboard_thermal(
        {
            "temps": [
                {
                    "drive": "sda",
                    "temp": 60,
                }
            ]
        }
    )

    assert frame.priority is Priority.CRITICAL


def test_thermal_dashboard_clamps_gauge():
    manager = make_manager()

    frame = manager._dashboard_thermal(
        {
            "temps": [
                {
                    "drive": "oven",
                    "temp": 500,
                }
            ]
        }
    )

    assert frame.lines == [
        "TEMP oven  500C ",
        "TMP ###### 100% ",
    ]


def test_thermal_dashboard_handles_no_data():
    manager = make_manager()

    frame = manager._dashboard_thermal(
        {
            "temps": [],
        }
    )

    assert frame.lines == [
        "THERMAL         ",
        "No Temp Data    ",
    ]
    assert frame.priority is Priority.INFO


def test_thermal_dashboard_returns_dashboard_frame():
    manager = make_manager()

    frame = manager._dashboard_thermal(
        {
            "temps": [
                {
                    "drive": "sda",
                    "temp": 40,
                }
            ]
        }
    )

    assert frame.mode == DisplayMode.DASHBOARD
    assert frame.interrupt is False
