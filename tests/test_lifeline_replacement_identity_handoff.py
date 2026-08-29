from truepanel.web.snapshot import _replacement_fault_for_session


def test_replacement_discovery_receives_persisted_drive_identity():
    identity = {
        "stable_key": "serial:test-stable-key",
        "mode": "serial_model",
        "confidence": "high",
        "source": "inventory_serial_cross_checked",
        "token": "test-token",
        "device": "sdc",
        "bay": 3,
        "model": "ST8000NE001",
        "serial_last4": "0001",
        "capacity_bytes": 8_000_000_000_000,
        "raw_serial_exposed": False,
        "raw_wwn_exposed": False,
    }
    session = {
        "original_fault": {
            "device": "sdc",
            "bay": 3,
            "serial_last4": "0001",
            "capacity_bytes": 8_000_000_000_000,
        },
        "drive_identity": identity,
        "last_session": {},
    }

    fault = _replacement_fault_for_session(session)

    assert fault["drive_identity"] == identity
    assert fault["drive_identity"] is not identity
