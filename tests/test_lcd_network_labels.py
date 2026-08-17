from pathlib import Path

from truepanel.mission_control.display_manager import (
    DisplayManager,
)
from truepanel.network_labels import (
    friendly_network_label,
    physical_interface_positions,
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

def test_physical_interface_positions_follow_sysfs_order(
    tmp_path,
):
    network_root = tmp_path / "net"
    network_root.mkdir()

    for name in (
        "enp121s0",
        "enp115s0",
        "enp120s0",
        "enp116s0",
    ):
        (
            network_root / name / "device"
        ).mkdir(
            parents=True
        )

    (network_root / "lo").mkdir()
    (network_root / "tailscale0").mkdir()

    assert physical_interface_positions(
        network_root
    ) == {
        "enp115s0": 1,
        "enp116s0": 2,
        "enp120s0": 3,
        "enp121s0": 4,
    }


def test_shared_network_labels_preserve_unknown_names():
    positions = {
        "enp116s0": 2,
    }

    assert friendly_network_label(
        "enp116s0",
        positions,
    ) == "Ethernet Port 2"
    assert friendly_network_label(
        "tailscale0",
        positions,
    ) == "Tailscale"
    assert friendly_network_label(
        "bridge0",
        positions,
    ) == "bridge0"


def test_physical_lcd_runtime_uses_friendly_network_labels():
    source = (
        Path(__file__).resolve().parents[1]
        / "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "physical_interface_positions()"
        in source
    )
    assert (
        "friendly_network_label("
        in source
    )
    assert (
        'ip_addresses.append((iface["ifname"], '
        "get_ipv4(iface)))"
        not in source
    )
