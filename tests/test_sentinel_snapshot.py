from truepanel.web import sentinel_snapshot


class TopologyProvider:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.payload


def service_with(provider):
    service = object.__new__(sentinel_snapshot.SentinelSnapshotService)
    service.sentinel_topology_provider = provider
    return service


def base_payload():
    return {
        "schema_version": 1,
        "read_only": True,
        "system": {"hostname": "BattleStation"},
        "storage": {
            "pools": [{"name": "HDDs", "health": "ONLINE"}],
            "devices": [],
            "smart": [],
        },
        "cargo_bay": {
            "summary": {"unresolved": 0},
            "groups": {"tv": [], "movies": []},
            "backup": {"tracking": False, "state": "NOT_TRACKED"},
        },
    }


def test_sentinel_snapshot_attaches_topology_and_assessment(monkeypatch):
    topology = {
        "schema_version": 1,
        "read_only": True,
        "source": "truenas.middleware",
        "datasets": [
            {
                "id": "HDDs/Movies",
                "name": "Movies",
                "pool": "HDDs",
                "type": "FILESYSTEM",
                "mountpoint": "/mnt/HDDs/Movies",
                "locked": False,
            }
        ],
        "applications": [],
        "relationships": [],
    }
    provider = TopologyProvider(payload=topology)
    service = service_with(provider)

    monkeypatch.setattr(
        sentinel_snapshot._SnapshotService,
        "status",
        lambda self: base_payload(),
    )

    payload = service.status()

    assert provider.calls == 1
    assert payload["sentinel_topology"]["available"] is True
    assert payload["sentinel_topology"]["datasets"][0]["id"] == "HDDs/Movies"
    assert payload["sentinel"]["read_only"] is True
    assert payload["sentinel"]["control_authority"] is False
    assert any(
        node["id"] == "dataset:HDDs/Movies"
        for node in payload["sentinel"]["graph"]["nodes"]
    )


def test_sentinel_snapshot_fails_closed_when_topology_provider_errors(monkeypatch):
    provider = TopologyProvider(error=OSError("middleware unavailable"))
    service = service_with(provider)

    monkeypatch.setattr(
        sentinel_snapshot._SnapshotService,
        "status",
        lambda self: base_payload(),
    )

    payload = service.status()

    assert provider.calls == 1
    assert payload["sentinel_topology"]["available"] is False
    assert payload["sentinel_topology"]["read_only"] is True
    assert payload["sentinel"]["control_authority"] is False
    assert any(
        "dataset-to-application dependencies" in unknown
        for unknown in payload["sentinel"]["assessment"]["unknowns"]
    )


def test_sentinel_snapshot_rejects_invalid_topology_payload(monkeypatch):
    provider = TopologyProvider(payload=["invalid"])
    service = service_with(provider)

    monkeypatch.setattr(
        sentinel_snapshot._SnapshotService,
        "status",
        lambda self: base_payload(),
    )

    payload = service.status()

    assert payload["sentinel_topology"]["available"] is False
    assert payload["sentinel_topology"]["relationships"] == []
    assert payload["sentinel"]["read_only"] is True
