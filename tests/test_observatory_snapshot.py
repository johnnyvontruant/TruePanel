from truepanel.web.observatory_snapshot import ObservatorySnapshotService
from truepanel.web.snapshot import SnapshotService


def test_observatory_snapshot_preserves_status_and_adds_activity(monkeypatch):
    monkeypatch.setattr(SnapshotService, "__init__", lambda self, *args, **kwargs: None)
    monkeypatch.setattr(
        SnapshotService,
        "status",
        lambda self: {
            "system": {"hostname": "battlestation"},
            "storage": {
                "zfs_activity": {
                    "scrub_running": True,
                    "resilver_running": False,
                    "percent": 40,
                }
            },
        },
    )

    service = ObservatorySnapshotService()
    payload = service.status()

    assert payload["system"] == {"hostname": "battlestation"}
    assert payload["activity"]["project"] == "OBSERVATORY"
    assert payload["activity"]["read_only"] is True
    assert payload["activity"]["production_mutation"] is False
    assert payload["activity"]["observations"][0]["kind"] == "zfs.scrub"
    assert payload["activity"]["observations"][0]["progress"] == 0.4
