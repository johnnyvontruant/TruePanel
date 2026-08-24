from truepanel.guidance import guidance_for_snapshot
from truepanel.guidance.storage_evidence import parse_zpool_status
from truepanel.lifeline import LifelineSessionStore


STATUS = """
  pool: HDDs
 state: DEGRADED
config:

        NAME                      STATE     READ WRITE CKSUM
        HDDs                      DEGRADED     0     0     0
          raidz1-0                DEGRADED     0     0     0
            /dev/sda1             ONLINE       0     0     0
            /dev/sdb1             ONLINE       0     0     0
            15571478626791065431  UNAVAIL      0     0     0  was /dev/disk/by-partuuid/389d5fd4-8899-434f-b171-ef29d8937033
            /dev/sde1             ONLINE       0     0     0
            /dev/sdd1             ONLINE       0     0     0
            /dev/sdf1             ONLINE       0     0     0

errors: No known data errors
"""


def payload():
    records = parse_zpool_status(STATUS)
    return {
        "storage": {
            "pools": [{"name": "HDDs", "health": "DEGRADED"}],
            "devices": records,
            "zfs_activity": {
                "scrub_running": True,
                "resilver_running": False,
            },
        }
    }


def test_missing_by_partuuid_member_stays_logical_not_physical():
    source = payload()
    guidance = guidance_for_snapshot(source)
    disk = next(item for item in guidance if item["code"] == "storage.disk_faulted")
    evidence = disk["runtime"]["evidence"]
    gate = disk["runtime"]["action_gate"]

    assert evidence["member_id"] == "15571478626791065431"
    assert evidence["historical_path"] == (
        "/dev/disk/by-partuuid/389d5fd4-8899-434f-b171-ef29d8937033"
    )
    assert evidence["device"] is None
    assert evidence["bay"] is None
    assert evidence["remaining_redundancy"] == 0
    assert disk["runtime"]["phase"] == "identify"
    assert "device_not_verified" in gate["blocked_by"]
    assert "physical_bay_not_verified" in gate["blocked_by"]
    assert gate["physical_service_ready"] is False
    assert gate["destructive_actions_ready"] is False


def test_missing_logical_member_opens_identify_session_without_fake_device(tmp_path):
    source = payload()
    source["operator_guidance"] = guidance_for_snapshot(source)

    store = LifelineSessionStore(path=tmp_path / "lifeline.json", clock=lambda: 100.0)
    observed = store.observe(source)
    sessions = observed["lifeline"]["sessions"]

    assert len(sessions) == 1
    session = sessions[0]
    assert session["fault_key"] == "drive:HDDs:raidz1-0:15571478626791065431"
    assert session["original_fault"]["member_id"] == "15571478626791065431"
    assert session["original_fault"]["device"] is None
    assert session["original_fault"]["bay"] is None
    assert session["last_session"]["phase"] == "identify"
    assert session["last_session"]["target"]["member_id"] == "15571478626791065431"
    assert session["last_session"]["target"]["device"] is None
    assert session["last_session"]["can_identify_bay"] is False
    assert session["last_session"]["can_begin_physical_service"] is False
    assert session["last_session"]["can_execute_replacement"] is False
