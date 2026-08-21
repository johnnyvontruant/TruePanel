from truepanel.lifeline import LifelineSessionStore


class Clock:
    def __init__(self):
        self.now = 1_000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += float(seconds)


def fault_payload(*, resilver=False, percent=None):
    activity = {
        "resilver_running": resilver,
        "percent": percent,
    }
    evidence = {
        "pool": "HDDs",
        "pool_state": "DEGRADED",
        "vdev": "raidz1-0",
        "vdev_topology": "RAIDZ1",
        "remaining_redundancy": 0,
        "bay": 3,
        "device": "sdc",
        "model": "ST8000NE001",
        "serial_last4": "MW4K",
        "capacity_bytes": 8_000_000_000_000,
        "zfs_state": "FAULTED",
        "resilver_state": activity,
    }
    return {
        "storage": {
            "pools": [{"name": "HDDs", "health": "DEGRADED"}],
            "zfs_activity": activity,
        },
        "operator_guidance": [
            {
                "code": "storage.disk_faulted",
                "runtime": {"evidence": evidence},
            }
        ],
    }


def healthy_payload():
    return {
        "storage": {
            "pools": [{"name": "HDDs", "health": "ONLINE"}],
            "zfs_activity": {"resilver_running": False},
        },
        "operator_guidance": [],
    }


def only_session(payload):
    sessions = payload["lifeline"]["sessions"]
    assert len(sessions) == 1
    return sessions[0]


def test_lifeline_drive_repair_round_trip_is_deterministic(tmp_path):
    clock = Clock()
    path = tmp_path / "lifeline.json"
    store = LifelineSessionStore(path=path, clock=clock)

    # T+0: Kobayashi detects and independently correlates the fault.
    detected = store.observe(fault_payload())
    session = only_session(detected)
    session_id = session["id"]
    assert session["last_session"]["phase"] == "prepare"
    assert session["last_session"]["can_identify_bay"] is True
    assert session["last_session"]["can_begin_physical_service"] is False

    # T+60: exact chassis procedure is verified from a source-backed profile.
    clock.advance(60)
    store.set_service_procedure_verified(
        session_id,
        verified=True,
        profile="qnap-tvs-x71",
        source="QNAP TVS-x71 Series Hardware User Manual",
    )
    store.acknowledge(session_id, "backup_state", True)
    prepared = store.observe(fault_payload())
    session = only_session(prepared)
    assert session["last_session"]["phase"] == "service_ready"
    assert session["last_session"]["can_begin_physical_service"] is True

    # T+120: an undersized replacement is detected and explicitly rejected.
    clock.advance(60)
    store.set_replacement_candidates(
        session_id,
        [
            {
                "device": "sdh",
                "model": "TEST-7TB",
                "capacity_bytes": 7_000_000_000_000,
                "member_of_pool": False,
                "contains_preserved_data": False,
            }
        ],
    )
    rejected = store.observe(fault_payload())
    session = only_session(rejected)
    assert session["last_session"]["phase"] == "validate_replacement"
    assert (
        "replacement_capacity_too_small"
        in session["last_session"]["replacement"]["reasons"]
    )

    # T+180: a valid replacement is present. Planning reaches the authority
    # boundary, but there is still no storage-write endpoint in Lifeline.
    clock.advance(60)
    store.set_replacement_candidates(
        session_id,
        [
            {
                "device": "sdh",
                "model": "ST8000NE001",
                "capacity_bytes": 8_000_000_000_000,
                "member_of_pool": False,
                "contains_preserved_data": False,
            }
        ],
    )
    replacement_ready = store.observe(fault_payload())
    session = only_session(replacement_ready)
    assert session["last_session"]["phase"] == "replacement_ready"
    assert session["last_session"]["replacement"]["valid"] is True
    assert session["last_session"]["can_execute_replacement"] is False

    # T+240: an external/guarded TrueNAS workflow has begun recovery. Lifeline
    # automatically switches from service planning to recovery monitoring.
    clock.advance(60)
    recovering = store.observe(fault_payload(resilver=True, percent=31))
    session = only_session(recovering)
    assert session["last_session"]["phase"] == "monitor_recovery"
    assert session["last_session"]["recovery_in_progress"] is True
    assert session["last_session"]["can_begin_physical_service"] is False

    # T+300..420: the fault card disappears when ZFS is healthy. Lifeline does
    # not vanish with it; three consecutive healthy observations are required.
    clock.advance(60)
    verify_one = store.observe(healthy_payload())
    assert only_session(verify_one)["healthy_observations"] == 1
    assert only_session(verify_one)["status"] == "active"

    clock.advance(60)
    verify_two = store.observe(healthy_payload())
    assert only_session(verify_two)["healthy_observations"] == 2
    assert only_session(verify_two)["status"] == "active"

    clock.advance(60)
    completed = store.observe(healthy_payload())
    session = only_session(completed)
    assert session["healthy_observations"] == 3
    assert session["status"] == "completed"
    assert session["last_session"]["phase"] == "complete"
    assert session["last_session"]["recovery_verified"] is True

    # A service restart still retains the closed repair record.
    restarted = LifelineSessionStore(path=path, clock=clock)
    persisted = only_session({"lifeline": restarted.snapshot()})
    assert persisted["status"] == "completed"
    assert persisted["original_fault"]["serial_last4"] == "MW4K"
