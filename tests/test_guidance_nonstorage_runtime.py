from truepanel.guidance.runtime import guidance_for_snapshot


def codes(payload):
    return [
        item["code"]
        for item in guidance_for_snapshot(payload)
    ]


def guidance(payload, code):
    for item in guidance_for_snapshot(payload):
        if item["code"] == code:
            return item
    raise AssertionError(f"missing guidance code: {code}")


def test_monitored_fan_stall_publishes_safe_diagnostic_guidance():
    payload = {
        "fans": {
            "available": True,
            "channels": [
                {
                    "number": 1,
                    "label": "Rear Fan 1",
                    "monitored": True,
                    "rpm": 0,
                    "alarm": True,
                    "consecutive_failures": 3,
                },
                {
                    "number": 2,
                    "label": "Rear Fan 2",
                    "monitored": True,
                    "rpm": 1510,
                    "alarm": False,
                },
                {
                    "number": 3,
                    "label": "Unused Header",
                    "monitored": False,
                    "rpm": 0,
                    "alarm": True,
                },
            ],
        }
    }

    item = guidance(payload, "cooling.fan_stall")
    runtime = item["runtime"]
    evidence = runtime["evidence"]

    assert evidence["fan_label"] == "Rear Fan 1"
    assert evidence["fan_channel"] == 1
    assert evidence["current_rpm"] == 0
    assert evidence["other_fan_rpm"] == [
        {"label": "Rear Fan 2", "rpm": 1510}
    ]
    assert runtime["phase"] == "diagnose"
    assert runtime["action_gate"]["safe_checks"] is True
    assert runtime["action_gate"]["physical_service_ready"] is False
    assert runtime["action_gate"]["destructive_actions_ready"] is False


def test_unmonitored_zero_rpm_channel_does_not_create_fan_guidance():
    payload = {
        "fans": {
            "available": True,
            "channels": [
                {
                    "number": 3,
                    "label": "Unused Header",
                    "monitored": False,
                    "rpm": 0,
                    "alarm": True,
                }
            ],
        }
    }

    assert "cooling.fan_stall" not in codes(payload)


def test_primary_link_loss_publishes_network_guidance_with_alt_path():
    payload = {
        "network": [
            {
                "name": "enp116s0",
                "label": "Ethernet Port 2",
                "kind": "lan",
                "primary": True,
                "link_up": False,
                "operstate": "DOWN",
                "address": None,
            },
            {
                "name": "tailscale0",
                "label": "Tailscale",
                "kind": "tailscale",
                "primary": False,
                "link_up": True,
                "operstate": "UNKNOWN",
                "address": "100.81.56.60",
            },
        ]
    }

    item = guidance(payload, "network.link_down")
    evidence = item["runtime"]["evidence"]

    assert evidence["interface"] == "enp116s0"
    assert evidence["label"] == "Ethernet Port 2"
    assert evidence["primary"] is True
    assert evidence["tailscale_reachable"] is True
    assert evidence["other_reachable_interfaces"] == ["Tailscale"]
    assert item["runtime"]["action_gate"]["destructive_actions_ready"] is False


def test_unused_down_lan_ports_do_not_create_network_guidance():
    payload = {
        "network": [
            {
                "name": "enp115s0",
                "label": "Ethernet Port 1",
                "kind": "lan",
                "primary": False,
                "link_up": False,
                "operstate": "DOWN",
            },
            {
                "name": "enp116s0",
                "label": "Ethernet Port 2",
                "kind": "lan",
                "primary": True,
                "link_up": True,
                "operstate": "UP",
            },
            {
                "name": "enp120s0",
                "label": "Ethernet Port 3",
                "kind": "lan",
                "primary": False,
                "link_up": False,
                "operstate": "DOWN",
            },
        ]
    }

    assert "network.link_down" not in codes(payload)


def test_unavailable_front_panel_publishes_narrow_recovery_guidance():
    payload = {
        "lcd": {
            "available": False,
            "reader": {
                "port": "/dev/ttyS1",
                "connected": False,
                "healthy": False,
                "dispatcher_alive": True,
                "last_healthy_at": 1234.5,
            },
        }
    }

    item = guidance(payload, "front_panel.lcd_unavailable")
    evidence = item["runtime"]["evidence"]

    assert evidence == {
        "serial_device": "/dev/ttyS1",
        "reader_connected": False,
        "last_successful_io": 1234.5,
        "dispatcher_alive": True,
        "mission_control_reachable": True,
    }
    assert item["runtime"]["phase"] == "diagnose"
    assert item["runtime"]["action_gate"]["physical_service_ready"] is False
    assert item["runtime"]["action_gate"]["destructive_actions_ready"] is False


def test_healthy_nonstorage_telemetry_adds_no_guidance_cards():
    payload = {
        "fans": {
            "available": True,
            "channels": [
                {
                    "number": 1,
                    "label": "Rear Fan 1",
                    "monitored": True,
                    "rpm": 1500,
                    "alarm": False,
                }
            ],
        },
        "network": [
            {
                "name": "enp116s0",
                "label": "Ethernet Port 2",
                "kind": "lan",
                "primary": True,
                "link_up": True,
                "operstate": "UP",
            }
        ],
        "lcd": {
            "available": True,
            "reader": {
                "connected": True,
                "healthy": True,
                "dispatcher_alive": True,
            },
        },
    }

    assert guidance_for_snapshot(payload) == []
