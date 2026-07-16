from truepanel.mission_control.constants import Priority
from truepanel.mission_control.display_manager import (
    DisplayManager,
    DisplayMode,
)


class FakeMission:
    def evaluate(self, state):
        raise AssertionError(
            "Performance dashboard should not evaluate mission events"
        )


class FakeAlertManager:
    pass


class EmptyRegistry:
    dashboard_pages = []


def make_manager():
    return DisplayManager(
        mission=FakeMission(),
        alert_manager=FakeAlertManager(),
        registry=EmptyRegistry(),
    )


def test_performance_dashboard_uses_compact_bars():
    manager = make_manager()

    frame = manager._dashboard_performance(
        {
            "cpu_percent": 50,
            "ram_percent": 75,
        }
    )

    assert frame.lines == [
        "CPU ###---  50% ",
        "RAM #####-  75% ",
    ]


def test_performance_dashboard_lines_are_lcd_width():
    manager = make_manager()

    frame = manager._dashboard_performance(
        {
            "cpu_percent": 100,
            "ram_percent": 100,
        }
    )

    assert all(
        len(line) == 16
        for line in frame.lines
    )


def test_performance_dashboard_clamps_values():
    manager = make_manager()

    frame = manager._dashboard_performance(
        {
            "cpu_percent": -20,
            "ram_percent": 900,
        }
    )

    assert frame.lines == [
        "CPU ------   0% ",
        "RAM ###### 100% ",
    ]


def test_performance_dashboard_records_history():
    manager = make_manager()

    manager._dashboard_performance(
        {
            "cpu_percent": 35,
            "ram_percent": 70,
        }
    )

    manager._dashboard_performance(
        {
            "cpu_percent": 80,
            "ram_percent": 50,
        }
    )

    assert manager.performance_history == [
        70,
        80,
    ]


def test_performance_history_is_limited_to_sixteen():
    manager = make_manager()

    for value in range(20):
        manager._dashboard_performance(
            {
                "cpu_percent": value,
                "ram_percent": 0,
            }
        )

    assert manager.performance_history == list(
        range(4, 20)
    )


def test_performance_dashboard_warns_at_high_usage():
    manager = make_manager()

    frame = manager._dashboard_performance(
        {
            "cpu_percent": 90,
            "ram_percent": 20,
        }
    )

    assert frame.priority is Priority.WARNING


def test_performance_dashboard_is_info_below_threshold():
    manager = make_manager()

    frame = manager._dashboard_performance(
        {
            "cpu_percent": 89,
            "ram_percent": 89,
        }
    )

    assert frame.priority is Priority.INFO


def test_performance_dashboard_returns_dashboard_frame():
    manager = make_manager()

    frame = manager._dashboard_performance(
        {
            "cpu_percent": 20,
            "ram_percent": 30,
        }
    )

    assert frame.mode == DisplayMode.DASHBOARD
    assert frame.interrupt is False
