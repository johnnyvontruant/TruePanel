from truepanel.web.snapshot import SnapshotService


class Collector:
    def update(self):
        return {
            "pools": [
                {
                    "name": "HDDs",
                    "health": "DEGRADED",
                }
            ],
            "storage_devices": [
                {
                    "pool": "HDDs",
                    "vdev": "raidz1-0",
                    "vdev_topology": "RAIDZ1",
                    "remaining_redundancy": 0,
                    "device": "sdc",
                    "physical_bay": 3,
                    "model": "ST8000NE001",
                    "serial_last4": "MW4K",
                    "capacity_bytes": 8_000_000_000_000,
                    "present": True,
                    "zfs_state": "FAULTED",
                    "read_errors": 4,
                    "write_errors": 0,
                    "checksum_errors": 1,
                }
            ],
            "zfs_activity": {
                "resilver_running": False,
            },
        }


def config(*, model):
    return {
        "hardware": {
            "lifeline": {
                "service_profile": "qnap-tvs-x71",
                "chassis_model": model,
            }
        },
        "history": {},
    }


def disk_session(payload):
    item = next(
        item
        for item in payload["operator_guidance"]
        if item["code"] == "storage.disk_faulted"
    )
    return item["repair_session"]


def test_explicit_tvs671_profile_verifies_service_provenance(tmp_path):
    service = SnapshotService(
        collector=Collector(),
        config=config(model="TVS-671"),
        lifeline_path=tmp_path / "lifeline.json",
        fan_status_provider=lambda: {},
        clock=lambda: 100.0,
    )

    payload = service.status()
    ledger = payload["lifeline"]
    session = ledger["sessions"][0]

    assert ledger["service_profile"]["selected_model"] == "TVS-671"
    assert session["context"]["service_procedure_verified"] is True
    assert session["context"]["service_profile"] == "qnap-tvs-x71"
    assert session["context"]["service_source"] == (
        "QNAP TVS-x71 Series Hardware User Manual"
    )
    assert disk_session(payload)["phase"] == "prepare"


def test_uncovered_model_keeps_physical_service_locked(tmp_path):
    service = SnapshotService(
        collector=Collector(),
        config=config(model="TVS-872XT"),
        lifeline_path=tmp_path / "lifeline.json",
        fan_status_provider=lambda: {},
        clock=lambda: 100.0,
    )

    payload = service.status()
    session = payload["lifeline"]["sessions"][0]

    assert "service_profile" not in payload["lifeline"]
    assert session["context"]["service_procedure_verified"] is False
    assert (
        "service_procedure"
        in session["last_session"]["blocked_by"]
    )
