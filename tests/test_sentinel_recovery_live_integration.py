from truepanel.web import sentinel_snapshot


class TopologyProvider:
    def snapshot(self):
        return {
            "schema_version": 1,
            "read_only": True,
            "source": "truenas.middleware",
            "available": True,
            "datasets": [],
            "applications": [],
            "relationships": [],
        }


def _guidance(device="/dev/sdc"):
    return {
        "code": "storage.smart_warning",
        "title": "Critical drive-health evidence detected",
        "severity": "critical",
        "summary": "Inspect the drive evidence.",
        "runtime": {
            "active": True,
            "evidence": {"device": device, "bay": 3},
        },
        "recovery": {
            "schema_version": 1,
            "incident_id": "recovery:smart-sdc",
            "code": "storage.smart_warning",
            "state": "diagnosing",
            "severity": "critical",
            "explanation": "Inspect the drive evidence.",
            "evidence": {"device": device, "bay": 3},
            "verification": {
                "strategy": "smart_and_zfs_recheck",
                "status": "pending",
            },
            "action_gate": {
                "safe_checks": True,
                "physical_service_ready": False,
                "destructive_actions_ready": False,
                "blocked_by": ["replacement_candidate_not_validated"],
            },
        },
    }


def _base_payload(guidance_device="/dev/sdc"):
    return {
        "schema_version": 1,
        "read_only": True,
        "system": {"hostname": "BattleStation"},
        "storage": {
            "pools": [{"name": "HDDs", "health": "ONLINE"}],
            "devices": [
                {
                    "device": "/dev/sdc",
                    "pool": "HDDs",
                    "vdev": "raidz1-0",
                    "physical_bay": 3,
                    "zfs_state": "ONLINE",
                }
            ],
            "smart": [
                {
                    "device": "/dev/sdc",
                    "health": "FAILED",
                    "pending": 2,
                }
            ],
        },
        "operator_guidance": [_guidance(guidance_device)],
    }


def _service():
    service = object.__new__(sentinel_snapshot.SentinelSnapshotService)
    service.sentinel_topology_provider = TopologyProvider()
    return service


def test_live_status_links_exact_pathfinder_device_reference(monkeypatch):
    monkeypatch.setattr(
        sentinel_snapshot._SnapshotService,
        "status",
        lambda self: _base_payload(),
    )

    payload = _service().status()

    explanation = payload["sentinel"]["explanations"][0]
    assert explanation["source_device"] == "/dev/sdc"
    assert explanation["recovery"]["available"] is True
    assert explanation["recovery"]["authority"] is False
    assert explanation["recovery"]["references"][0]["incident_id"] == (
        "recovery:smart-sdc"
    )


def test_live_status_does_not_cross_link_different_guidance_device(monkeypatch):
    monkeypatch.setattr(
        sentinel_snapshot._SnapshotService,
        "status",
        lambda self: _base_payload("/dev/sdd"),
    )

    payload = _service().status()

    explanation = payload["sentinel"]["explanations"][0]
    assert explanation["source_device"] == "/dev/sdc"
    assert explanation["recovery"]["available"] is False
    assert explanation["recovery"]["references"] == []
