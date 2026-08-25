from truepanel.guidance import guidance_for_snapshot
from truepanel.web.snapshot import SnapshotService


class EvidenceProvider:
    def __init__(self, records=None, error=None):
        self.calls = 0
        self._records = list(records or [])
        self._error = error

    def records(self):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return list(self._records)


def service(provider):
    instance = object.__new__(SnapshotService)
    instance.storage_evidence_provider = provider
    return instance


def test_storage_payload_forwards_existing_smart_and_zfs_activity():
    provider = EvidenceProvider()
    snapshot = service(provider)
    state = {
        "pools": [{"name": "HDDs", "health": "ONLINE"}],
        "temps": [{"device": "sda", "temperature_c": 34}],
        "alerts": [],
        "smart": [{"drive": "sda", "health": "PASSED"}],
        "zfs_activity": {"resilver_running": False},
    }

    payload = snapshot._storage_payload(state)

    assert payload["pools"] == state["pools"]
    assert payload["temperatures"] == state["temps"]
    assert payload["smart"] == state["smart"]
    assert payload["zfs_activity"] == state["zfs_activity"]
    assert payload["devices"] == []
    assert provider.calls == 0


def test_smart_warning_resolves_exact_member_evidence_while_pool_is_online():
    provider = EvidenceProvider(
        [
            {
                "pool": "HDDs",
                "vdev": "raidz1-0",
                "vdev_topology": "RAIDZ1",
                "remaining_redundancy": 1,
                "physical_bay": 3,
                "device": "sdc",
                "model": "ST8000NE001",
                "serial_last4": "MW6D",
                "zfs_state": "ONLINE",
                "present": True,
            }
        ]
    )
    snapshot = service(provider)

    payload = snapshot._storage_payload(
        {
            "pools": [{"name": "HDDs", "health": "ONLINE"}],
            "smart": [
                {
                    "drive": "sdc",
                    "health": "PASSED",
                    "pending": 1608,
                    "offline_uncorrectable": 1608,
                    "reallocated": 15952,
                    "reported_uncorrect": 905,
                    "critical_warning": "0x00",
                }
            ],
        }
    )

    assert provider.calls == 1
    assert payload["devices"][0]["device"] == "sdc"

    smart = payload["smart"][0]
    assert smart["pool"] == "HDDs"
    assert smart["vdev"] == "raidz1-0"
    assert smart["physical_bay"] == 3
    assert smart["zfs_state"] == "ONLINE"
    assert smart["serial_last4"] == "MW6D"

    guidance = guidance_for_snapshot({"storage": payload})
    smart_guidance = next(
        item
        for item in guidance
        if item["code"] == "storage.smart_warning"
    )
    assert smart_guidance["runtime"]["evidence"]["bay"] == 3
    assert smart_guidance["runtime"]["evidence"]["pool"] == "HDDs"
    assert smart_guidance["runtime"]["action_gate"]["blocked_by"] == []


def test_smart_warning_never_uses_unverified_physical_identity():
    provider = EvidenceProvider(
        [
            {
                "pool": "HDDs",
                "vdev": "raidz1-0",
                "physical_bay": None,
                "device": "sdc",
                "zfs_state": "ONLINE",
                "present": False,
            }
        ]
    )
    snapshot = service(provider)

    payload = snapshot._storage_payload(
        {
            "pools": [{"name": "HDDs", "health": "ONLINE"}],
            "smart": [
                {
                    "drive": "sdc",
                    "health": "PASSED",
                    "pending": 1,
                    "critical_warning": "0x00",
                }
            ],
        }
    )

    assert provider.calls == 1
    assert "pool" not in payload["smart"][0]
    assert "physical_bay" not in payload["smart"][0]
    assert "zfs_state" not in payload["smart"][0]


def test_degraded_pool_resolves_member_evidence_lazily():
    provider = EvidenceProvider(
        [
            {
                "pool": "HDDs",
                "vdev": "raidz1-0",
                "physical_bay": 3,
                "device": "sdc",
                "zfs_state": "FAULTED",
            }
        ]
    )
    snapshot = service(provider)

    payload = snapshot._storage_payload(
        {"pools": [{"name": "HDDs", "health": "DEGRADED"}]}
    )

    assert provider.calls == 1
    assert payload["devices"][0]["physical_bay"] == 3
    assert payload["devices"][0]["device"] == "sdc"


def test_evidence_provider_failure_never_breaks_status_payload():
    provider = EvidenceProvider(error=OSError("zpool unavailable"))
    snapshot = service(provider)

    payload = snapshot._storage_payload(
        {"pools": [{"name": "HDDs", "health": "DEGRADED"}]}
    )

    assert provider.calls == 1
    assert payload["devices"] == []


def test_holodeck_can_supply_member_evidence_without_touching_live_resolver():
    provider = EvidenceProvider(error=AssertionError("resolver must not run"))
    snapshot = service(provider)
    supplied = [
        {
            "pool": "HDDs",
            "vdev": "raidz1-0",
            "physical_bay": 3,
            "device": "sdc",
            "zfs_state": "FAULTED",
        }
    ]

    payload = snapshot._storage_payload(
        {
            "pools": [{"name": "HDDs", "health": "DEGRADED"}],
            "storage_devices": supplied,
        }
    )

    assert payload["devices"] is supplied
    assert provider.calls == 0
