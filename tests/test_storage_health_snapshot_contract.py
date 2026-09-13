from truepanel.web.snapshot import SnapshotService


class FakeCollector:
    def __init__(self, state):
        self.state = state

    def update(self):
        return dict(self.state)


def test_snapshot_marks_bay3_style_smart_evidence_critical(tmp_path):
    service = SnapshotService(
        collector=FakeCollector(
            {
                "pools": [
                    {
                        "name": "HDDs",
                        "health": "ONLINE",
                    }
                ],
                "smart": [
                    {
                        "device": "sdc",
                        "health": "PASSED",
                        "pending": 1608,
                        "offline_uncorrectable": 1608,
                        "reallocated": 16176,
                    }
                ],
                "storage_devices": [
                    {
                        "device": "sdc",
                        "present": True,
                        "physical_bay": 3,
                        "pool": "HDDs",
                        "zfs_state": "ONLINE",
                    }
                ],
            }
        ),
        config={},
        history_path=tmp_path / "history.jsonl",
    )

    payload = service.status()

    smart = payload["storage"]["smart"][0]

    assert smart["physical_bay"] == 3
    assert smart["zfs_state"] == "ONLINE"
    assert smart["health_state"] == "critical"
    assert smart["health_message"] == "pending sectors: 1608"


def test_snapshot_preserves_unknown_when_smart_measurements_missing(tmp_path):
    service = SnapshotService(
        collector=FakeCollector(
            {
                "pools": [],
                "smart": [
                    {
                        "device": "sda",
                    }
                ],
                "storage_devices": [
                    {
                        "device": "sda",
                        "present": True,
                        "physical_bay": 1,
                    }
                ],
            }
        ),
        config={},
        history_path=tmp_path / "history.jsonl",
    )

    payload = service.status()

    smart = payload["storage"]["smart"][0]

    assert smart["health_state"] == "unknown"
    assert smart["health_message"] == "no health telemetry available"
