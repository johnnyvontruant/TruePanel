import json
from pathlib import Path

import collector as collector_module
from collector import TruePanelCollector


class FakeCompletedProcess:
    def __init__(self, payload):
        self.stdout = json.dumps(payload)


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
            },
            "docker0": {
                "download_mb": 99.0,
                "upload_mb": 99.0,
            },
            "tailscale0": {
                "download_mb": 0.1,
                "upload_mb": 0.0,
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
        "link_up": True,
        "operstate": "UNKNOWN",
        "primary": False,
        "kind": "tailscale",
    }


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
                }
            }
        )
        == {}
    )
