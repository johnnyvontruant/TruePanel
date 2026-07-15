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


def test_capacity_dashboard_uses_fullest_pool():
    manager = make_manager()

    frame = manager._dashboard_capacity(
        {
            "pools": [
                {
                    "name": "tank",
                    "capacity": "82%",
                },
                {
                    "name": "backup",
                    "capacity": "40%",
                },
            ]
        }
    )

    assert frame.lines == [
        "POOL tank    82%",
        "USE #####-  82% ",
    ]


def test_capacity_dashboard_warning_threshold():
    manager = make_manager()

    frame = manager._dashboard_capacity(
        {
            "pools": [
                {
                    "name": "tank",
                    "capacity": "85%",
                }
            ]
        }
    )

    assert frame.priority is Priority.WARNING


def test_capacity_dashboard_critical_threshold():
    manager = make_manager()

    frame = manager._dashboard_capacity(
        {
            "pools": [
                {
                    "name": "tank",
                    "capacity": "95%",
                }
            ]
        }
    )

    assert frame.priority is Priority.CRITICAL


def test_capacity_dashboard_no_data():
    manager = make_manager()

    frame = manager._dashboard_capacity(
        {
            "pools": [],
        }
    )

    assert frame.lines == [
        "CAPACITY        ",
        "No Pool Data    ",
    ]
