from truepanel.mission_control.display_manager import (
    DisplayManager,
)


class FakeDisplay:
    def __init__(self, interface):
        self.interface = interface
        self.network_interface_index = 0

    def _physical_network_interfaces(self):
        return [self.interface]

    @staticmethod
    def center_text(value):
        return value

    @staticmethod
    def make_frame(
        title,
        value,
        priority,
    ):
        return {
            "title": title,
            "value": value,
            "priority": priority,
        }


def test_lcd_uses_friendly_ethernet_port_name():
    display = FakeDisplay(
        {
            "position": 2,
            "name": "enp116s0",
            "ipv4": "192.168.0.108",
            "link_up": True,
            "operstate": "UP",
        }
    )

    frame = DisplayManager._dashboard_network(
        display,
        {},
    )

    assert frame["title"] == "Ethernet Port 2 ↑"
    assert frame["value"] == "192.168.0.108"


def test_lcd_friendly_port_name_reports_link_down():
    display = FakeDisplay(
        {
            "position": 1,
            "name": "enp115s0",
            "ipv4": None,
            "link_up": False,
            "operstate": "DOWN",
        }
    )

    frame = DisplayManager._dashboard_network(
        display,
        {},
    )

    assert frame["title"] == "Ethernet Port 1 ↓"
    assert frame["value"] == "No IPv4 address"
