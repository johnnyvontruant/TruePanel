from copy import deepcopy

from truepanel.health import augment_status_snapshot


def make_status():
    return {
        "schema_version": 1,
        "read_only": True,
        "timestamp": 100.0,
        "system": {
            "hostname": "BattleStation",
            "cpu_percent": 20.0,
        },
        "storage": {
            "pools": [
                {
                    "name": "HDDs",
                    "health": "ONLINE",
                }
            ]
        },
        "network": [
            {
                "name": "enp116s0",
                "label": "Ethernet Port 2",
                "primary": True,
                "link_up": True,
            }
        ],
        "lcd": {
            "available": True,
            "stale": False,
            "reader": {
                "healthy": True,
                "connected": True,
            },
        },
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
            "control": {
                "available": True,
                "safety_hold": False,
                "recovery_pending": False,
            },
        },
        "capabilities": {
            "safety": {
                "read_only": True,
                "remote_writes_enabled": False,
            }
        },
    }


def test_augment_status_is_additive_and_does_not_mutate_source():
    source = make_status()
    before = deepcopy(source)

    augmented = augment_status_snapshot(source)

    assert source == before
    assert "health" not in source
    assert augmented["health"]["state"] == "NOMINAL"

    for key, value in before.items():
        assert augmented[key] == value


def test_augment_status_preserves_nested_object_identity():
    source = make_status()

    augmented = augment_status_snapshot(source)

    assert augmented["system"] is source["system"]
    assert augmented["storage"] is source["storage"]
    assert augmented["network"] is source["network"]
    assert augmented["lcd"] is source["lcd"]
    assert augmented["fans"] is source["fans"]
    assert augmented["capabilities"] is source["capabilities"]


def test_augment_status_surfaces_existing_fault_without_altering_telemetry():
    source = make_status()
    source["storage"]["pools"][0]["health"] = "DEGRADED"

    augmented = augment_status_snapshot(source)

    assert augmented["health"]["state"] == "DEGRADED"
    assert augmented["health"]["subsystems"]["storage"]["state"] == "DEGRADED"
    assert augmented["storage"] == source["storage"]


def test_augment_status_handles_missing_optional_sections_as_unknown():
    source = {
        "schema_version": 1,
        "read_only": True,
    }

    augmented = augment_status_snapshot(source)

    assert augmented["health"]["state"] == "UNKNOWN"
    assert augmented["health"]["unknown_subsystems"] == 6
