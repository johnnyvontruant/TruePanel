from truepanel.activity import ActivityProviderStatus, ActivitySnapshot
from truepanel.activity.web import mission_control_activity


class BrokenProvider:
    source = "broken"

    def snapshot(self):
        raise RuntimeError("provider secret must not escape")


class DuplicateZfsProvider:
    source = "zfs"

    def snapshot(self):
        return ActivitySnapshot(
            source=self.source,
            status=ActivityProviderStatus.AVAILABLE,
        )


def test_mission_control_activity_exposes_normalized_zfs_scrub():
    payload = {
        "storage": {
            "zfs_activity": {
                "scrub_running": True,
                "resilver_running": False,
                "percent": 60,
                "raw_status": "must remain outside the activity contract",
            }
        }
    }

    activity = mission_control_activity(payload)

    assert activity["project"] == "OBSERVATORY"
    assert activity["read_only"] is True
    assert activity["production_mutation"] is False
    assert activity["truncated"] is False
    assert activity["providers"][0]["source"] == "zfs"
    assert activity["providers"][0]["status"] == "available"
    assert activity["observations"] == [
        {
            "schema_version": 1,
            "source": "zfs",
            "kind": "zfs.scrub",
            "state": "active",
            "title": "ZFS scrub",
            "confidence": 1.0,
            "intensity": "moderate",
            "subtitle": "Storage integrity maintenance",
            "progress": 0.6,
            "started_at": None,
            "context": {},
            "evidence": ["storage.zfs_activity.scrub_running"],
        }
    ]
    assert "raw_status" not in str(activity)


def test_mission_control_activity_contains_optional_provider_failure():
    activity = mission_control_activity({}, providers=[BrokenProvider()])

    providers = {item["source"]: item for item in activity["providers"]}
    assert providers["broken"] == {
        "schema_version": 1,
        "source": "broken",
        "status": "unavailable",
        "observations": [],
    }
    assert providers["zfs"]["status"] == "available"
    assert activity["observations"] == []
    assert "secret" not in str(activity)


def test_mission_control_activity_fails_closed_on_registry_construction_error():
    activity = mission_control_activity({}, providers=[DuplicateZfsProvider()])

    assert activity == {
        "schema_version": 1,
        "project": "OBSERVATORY",
        "read_only": True,
        "production_mutation": False,
        "providers": [],
        "observations": [],
        "truncated": False,
        "unavailable": True,
    }
