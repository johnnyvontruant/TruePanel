import json
from pathlib import Path

import collector as collector_module
from collector import TruePanelCollector


class FakeCompletedProcess:
    def __init__(self, payload):
        self.stdout = json.dumps(payload)


def install_network_sysfs(monkeypatch, tmp_path, counters):
    physical = tmp_path / "net"
    physical.mkdir()

    for name, (rx, tx) in counters.items():
        interface = physical / name
        interface.mkdir()
        statistics = interface / "statistics"
        statistics.mkdir()
        (statistics / "rx_bytes").write_text(
            str(rx),
            encoding="utf-8",
        )
        (statistics / "tx_bytes").write_text(
            str(tx),
            encoding="utf-8",
        )

    real_path = Path

    def fake_path(value):
        if value == "/sys/class/net":
            return physical

        return real_path(value)

    monkeypatch.setattr(
        collector_module,
        "Path",
        fake_path,
    )

    return physical


def set_counters(root, name, rx, tx):
    statistics = root / name / "statistics"
    (statistics / "rx_bytes").write_text(
        str(rx),
        encoding="utf-8",
    )
    (statistics / "tx_bytes").write_text(
        str(tx),
        encoding="utf-8",
    )


def install_clock(monkeypatch, values):
    samples = iter(values)
    monkeypatch.setattr(
        collector_module.time,
        "monotonic",
        lambda: next(samples),
    )


def test_network_rates_first_sample_establishes_baseline(
    monkeypatch,
    tmp_path,
):
    install_network_sysfs(
        monkeypatch,
        tmp_path,
        {
            "enp116s0": (1000, 2000),
        },
    )
    install_clock(
        monkeypatch,
        [10.0],
    )

    collector = TruePanelCollector()

    assert collector.get_network_rates() == {}


def test_network_rates_use_monotonic_elapsed_time_and_publish_mbps(
    monkeypatch,
    tmp_path,
):
    root = install_network_sysfs(
        monkeypatch,
        tmp_path,
        {
            "enp116s0": (1_000_000, 2_000_000),
        },
    )
    install_clock(
        monkeypatch,
        [10.0, 12.0],
    )

    collector = TruePanelCollector()

    assert collector.get_network_rates() == {}

    set_counters(
        root,
        "enp116s0",
        2_000_000,
        2_250_000,
    )

    assert collector.get_network_rates() == {
        "enp116s0": {
            "download_mb": 0.5,
            "upload_mb": 0.1,
            "download_mbps": 4.0,
            "upload_mbps": 1.0,
        }
    }


def test_network_rates_sample_interfaces_independently(
    monkeypatch,
    tmp_path,
):
    root = install_network_sysfs(
        monkeypatch,
        tmp_path,
        {
            "enp116s0": (100, 200),
            "tailscale0": (500, 700),
        },
    )
    install_clock(
        monkeypatch,
        [1.0, 2.0],
    )

    collector = TruePanelCollector()
    assert collector.get_network_rates() == {}

    set_counters(root, "enp116s0", 1_000_100, 500_200)
    set_counters(root, "tailscale0", 250_500, 125_700)

    rates = collector.get_network_rates()

    assert rates["enp116s0"]["download_mbps"] == 8.0
    assert rates["enp116s0"]["upload_mbps"] == 4.0
    assert rates["tailscale0"]["download_mbps"] == 2.0
    assert rates["tailscale0"]["upload_mbps"] == 1.0


def test_network_rates_counter_reset_becomes_new_baseline(
    monkeypatch,
    tmp_path,
):
    root = install_network_sysfs(
        monkeypatch,
        tmp_path,
        {
            "enp116s0": (5_000_000, 6_000_000),
        },
    )
    install_clock(
        monkeypatch,
        [1.0, 2.0, 3.0],
    )

    collector = TruePanelCollector()
    assert collector.get_network_rates() == {}

    set_counters(root, "enp116s0", 100, 200)
    assert collector.get_network_rates() == {}

    set_counters(root, "enp116s0", 1_000_100, 500_200)
    rates = collector.get_network_rates()

    assert rates["enp116s0"]["download_mbps"] == 8.0
    assert rates["enp116s0"]["upload_mbps"] == 4.0


def test_network_rates_disappearing_interface_does_not_spike_on_return(
    monkeypatch,
    tmp_path,
):
    root = install_network_sysfs(
        monkeypatch,
        tmp_path,
        {
            "enp116s0": (1_000, 2_000),
        },
    )
    install_clock(
        monkeypatch,
        [1.0, 2.0, 3.0, 4.0],
    )

    collector = TruePanelCollector()
    assert collector.get_network_rates() == {}

    interface = root / "enp116s0"
    for child in (interface / "statistics").iterdir():
        child.unlink()
    (interface / "statistics").rmdir()
    interface.rmdir()

    assert collector.get_network_rates() == {}

    interface.mkdir()
    statistics = interface / "statistics"
    statistics.mkdir()
    (statistics / "rx_bytes").write_text("9000000", encoding="utf-8")
    (statistics / "tx_bytes").write_text("8000000", encoding="utf-8")

    assert collector.get_network_rates() == {}

    set_counters(root, "enp116s0", 9_001_000, 8_002_000)
    rates = collector.get_network_rates()

    assert rates["enp116s0"]["download_mbps"] == 0.01
    assert rates["enp116s0"]["upload_mbps"] == 0.02


def test_network_rates_nonpositive_elapsed_time_is_safe(
    monkeypatch,
    tmp_path,
):
    root = install_network_sysfs(
        monkeypatch,
        tmp_path,
        {
            "enp116s0": (100, 200),
        },
    )
    install_clock(
        monkeypatch,
        [5.0, 5.0],
    )

    collector = TruePanelCollector()
    assert collector.get_network_rates() == {}

    set_counters(root, "enp116s0", 10_000_100, 10_000_200)

    assert collector.get_network_rates() == {}


def test_network_telemetry_enriches_primary_lan_and_tailscale(
    monkeypatch,
    tmp_path,
):
    physical = tmp_path / "net"
    physical.mkdir()

    lan = physical / "enp116s0"
    lan.mkdir()
    (lan / "device").mkdir()

    docker = physical / "docker0"
    docker.mkdir()

    tailscale = physical / "tailscale0"
    tailscale.mkdir()

    real_path = Path

    def fake_path(value):
        if value == "/sys/class/net":
            return physical

        return real_path(value)

    monkeypatch.setattr(
        collector_module,
        "Path",
        fake_path,
    )

    def fake_run(command, **kwargs):
        if "address" in command:
            return FakeCompletedProcess(
                [
                    {
                        "ifname": "enp116s0",
                        "operstate": "UP",
                        "flags": [
                            "BROADCAST",
                            "LOWER_UP",
                        ],
                        "addr_info": [
                            {
                                "family": "inet",
                                "local": "192.168.0.108",
                            }
                        ],
                    },
                    {
                        "ifname": "docker0",
                        "operstate": "DOWN",
                        "flags": [],
                        "addr_info": [
                            {
                                "family": "inet",
                                "local": "172.16.0.1",
                            }
                        ],
                    },
                    {
                        "ifname": "tailscale0",
                        "operstate": "UNKNOWN",
                        "flags": [
                            "UP",
                            "LOWER_UP",
                        ],
                        "addr_info": [
                            {
                                "family": "inet",
                                "local": "100.81.56.60",
                            }
                        ],
                    },
                ]
            )

        return FakeCompletedProcess(
            [
                {
                    "dst": "default",
                    "gateway": "192.168.0.1",
                    "dev": "enp116s0",
                }
            ]
        )

    monkeypatch.setattr(
        collector_module.subprocess,
        "run",
        fake_run,
    )

    collector = TruePanelCollector()

    payload = collector.get_network_telemetry(
        {
            "enp116s0": {
                "download_mb": 12.3,
                "upload_mb": 1.7,
                "download_mbps": 103.18,
                "upload_mbps": 14.26,
            },
            "docker0": {
                "download_mb": 99.0,
                "upload_mb": 99.0,
                "download_mbps": 830.47,
                "upload_mbps": 830.47,
            },
            "tailscale0": {
                "download_mb": 0.1,
                "upload_mb": 0.0,
                "download_mbps": 0.84,
                "upload_mbps": 0.0,
            },
        }
    )

    assert set(payload) == {
        "enp116s0",
        "tailscale0",
    }

    assert payload["enp116s0"] == {
        "position": 1,
        "label": "Ethernet Port 1",
        "address": "192.168.0.108",
        "download_mb": 12.3,
        "upload_mb": 1.7,
        "download_mbps": 103.18,
        "upload_mbps": 14.26,
        "link_up": True,
        "operstate": "UP",
        "primary": True,
        "kind": "lan",
    }

    assert payload["tailscale0"] == {
        "position": None,
        "label": "Tailscale",
        "address": "100.81.56.60",
        "download_mb": 0.1,
        "upload_mb": 0.0,
        "download_mbps": 0.84,
        "upload_mbps": 0.0,
        "link_up": True,
        "operstate": "UNKNOWN",
        "primary": False,
        "kind": "tailscale",
    }


def test_network_telemetry_zeroes_rates_for_down_link(
    monkeypatch,
    tmp_path,
):
    physical = tmp_path / "net"
    physical.mkdir()
    lan = physical / "enp116s0"
    lan.mkdir()
    (lan / "device").mkdir()

    real_path = Path

    def fake_path(value):
        if value == "/sys/class/net":
            return physical
        return real_path(value)

    monkeypatch.setattr(collector_module, "Path", fake_path)

    def fake_run(command, **kwargs):
        if "address" in command:
            return FakeCompletedProcess(
                [
                    {
                        "ifname": "enp116s0",
                        "operstate": "DOWN",
                        "flags": [],
                        "addr_info": [],
                    }
                ]
            )
        return FakeCompletedProcess([])

    monkeypatch.setattr(
        collector_module.subprocess,
        "run",
        fake_run,
    )

    payload = TruePanelCollector().get_network_telemetry(
        {
            "enp116s0": {
                "download_mb": 12.3,
                "upload_mb": 1.7,
                "download_mbps": 103.18,
                "upload_mbps": 14.26,
            }
        }
    )

    assert payload["enp116s0"]["link_up"] is False
    assert payload["enp116s0"]["download_mb"] == 0.0
    assert payload["enp116s0"]["upload_mb"] == 0.0
    assert payload["enp116s0"]["download_mbps"] == 0.0
    assert payload["enp116s0"]["upload_mbps"] == 0.0


def test_network_telemetry_handles_ip_failure(
    monkeypatch,
):
    def fail_run(command, **kwargs):
        raise OSError("ip unavailable")

    monkeypatch.setattr(
        collector_module.subprocess,
        "run",
        fail_run,
    )

    collector = TruePanelCollector()

    assert (
        collector.get_network_telemetry(
            {
                "enp116s0": {
                    "download_mb": 1.0,
                    "upload_mb": 2.0,
                    "download_mbps": 8.39,
                    "upload_mbps": 16.78,
                }
            }
        )
        == {}
    )
