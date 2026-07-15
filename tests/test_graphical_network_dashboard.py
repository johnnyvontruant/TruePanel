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


def test_network_dashboard_renders_rates_and_history():
    manager = make_manager()

    frame = manager._dashboard_network(
        {
            "network": {
                "download_bytes_per_sec": 2048,
                "upload_bytes_per_sec": 1024,
            }
        }
    )

    assert frame.lines[0].strip() == "R    2K T    1K"
    assert frame.lines[1].startswith("NET ")
    assert len(frame.lines[1]) == 16
    assert manager.network_history == [
        3072.0,
    ]
    assert frame.priority is Priority.INFO


def test_network_dashboard_tracks_recent_samples():
    manager = make_manager()

    for value in range(20):
        manager._dashboard_network(
            {
                "network": {
                    "download_bytes_per_sec": value,
                    "upload_bytes_per_sec": 0,
                }
            }
        )

    assert manager.network_history == [
        float(value)
        for value in range(4, 20)
    ]


def test_network_dashboard_accepts_legacy_rate_keys():
    manager = make_manager()

    frame = manager._dashboard_network(
        {
            "network": {
                "rx_rate": 4096,
                "tx_rate": 2048,
            }
        }
    )

    assert frame.lines[0].strip() == "R    4K T    2K"
