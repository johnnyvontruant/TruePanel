import json

from truepanel.lifeline import LifelineSessionStore


def guidance_payload(*, pool_state="DEGRADED", resilver=False):
    return {
        "storage": {
            "pools": [{"name": "HDDs", "health": pool_state}],
            "zfs_activity": {"resilver_running": resilver},
        },
        "operator_guidance": [
            {
                "code": "storage.disk_faulted",
                "runtime": {
                    "evidence": {
                        "pool": "HDDs",
                        "pool_state": pool_state,
                        "vdev": "raidz1-0",
                        "vdev_topology": "RAIDZ1",
                        "remaining_redundancy": 0,
                        "device": "sdc",
                        "bay": 3,
                        "model": "ST8000NE001",
                        "serial_last4": "MW4K",
                        "capacity_bytes": 8_000_000_000_000,
                        "zfs_state": "FAULTED",
                        "resilver_state": {
                            "resilver_running": resilver,
                        },
                    }
                },
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


def test_fault_opens_persistent_session(tmp_path):
    path = tmp_path / "lifeline.json"
    store = LifelineSessionStore(path=path, clock=lambda: 100.0)

    payload = store.observe(guidance_payload())

    sessions = payload["lifeline"]["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["status"] == "active"
    assert sessions[0]["attempt"] == 1
    assert sessions[0]["id"].endswith(":attempt-1")
    assert sessions[0]["original_fault"]["serial_last4"] == "MW4K"
    assert sessions[0]["last_session"]["phase"] == "prepare"
    assert path.exists()


def test_session_survives_store_restart(tmp_path):
    path = tmp_path / "lifeline.json"
    first = LifelineSessionStore(path=path, clock=lambda: 100.0)
    first.observe(guidance_payload())

    second = LifelineSessionStore(path=path, clock=lambda: 200.0)
    snapshot = second.snapshot()

    assert len(snapshot["sessions"]) == 1
    assert snapshot["sessions"][0]["original_fault"]["device"] == "sdc"


def test_backup_acknowledgement_is_metadata_only_and_persistent(tmp_path):
    path = tmp_path / "lifeline.json"
    store = LifelineSessionStore(path=path, clock=lambda: 100.0)
    observed = store.observe(guidance_payload())
    session_id = observed["lifeline"]["sessions"][0]["id"]

    store.acknowledge(session_id, "backup_state", True)
    observed = store.observe(guidance_payload())
    session = observed["lifeline"]["sessions"][0]

    assert session["context"]["acknowledgements"]["backup_state"] is True
    assert session["last_session"]["phase"] == "prepare"
    assert "backup_acknowledgement" not in session["last_session"]["blocked_by"]


def test_unknown_acknowledgement_is_rejected(tmp_path):
    store = LifelineSessionStore(path=tmp_path / "lifeline.json")
    observed = store.observe(guidance_payload())
    session_id = observed["lifeline"]["sessions"][0]["id"]

    try:
        store.acknowledge(session_id, "replace_disk", True)
    except ValueError as error:
        assert "unsupported" in str(error)
    else:
        raise AssertionError("unsafe acknowledgement unexpectedly accepted")


def test_service_procedure_requires_separate_verified_provenance(tmp_path):
    store = LifelineSessionStore(path=tmp_path / "lifeline.json")
    observed = store.observe(guidance_payload())
    session_id = observed["lifeline"]["sessions"][0]["id"]

    store.set_service_procedure_verified(
        session_id,
        verified=True,
        profile="qnap-tvs-671",
        source="QNAP TVS-x71 Hardware Manual",
    )
    store.acknowledge(session_id, "backup_state", True)
    observed = store.observe(guidance_payload())
    session = observed["lifeline"]["sessions"][0]

    assert session["context"]["service_profile"] == "qnap-tvs-671"
    assert session["last_session"]["phase"] == "service_ready"


def test_replacement_candidate_validation_is_persisted(tmp_path):
    store = LifelineSessionStore(path=tmp_path / "lifeline.json")
    observed = store.observe(guidance_payload())
    session_id = observed["lifeline"]["sessions"][0]["id"]
    store.set_service_procedure_verified(session_id, verified=True)
    store.acknowledge(session_id, "backup_state", True)
    store.set_replacement_candidates(
        session_id,
        [
            {
                "device": "sdh",
                "capacity_bytes": 8_000_000_000_000,
                "member_of_pool": False,
                "contains_preserved_data": False,
            }
        ],
    )

    observed = store.observe(guidance_payload())
    session = observed["lifeline"]["sessions"][0]

    assert session["last_session"]["replacement"]["valid"] is True
    assert session["last_session"]["phase"] == "replacement_ready"
    assert session["last_session"]["can_execute_replacement"] is False


def test_session_does_not_close_on_single_healthy_observation(tmp_path):
    store = LifelineSessionStore(path=tmp_path / "lifeline.json")
    store.observe(guidance_payload())

    payload = store.observe(healthy_payload())
    session = payload["lifeline"]["sessions"][0]

    assert session["status"] == "active"
    assert session["healthy_observations"] == 1
    assert session["last_session"]["phase"] == "verify"


def test_three_consecutive_healthy_observations_close_session(tmp_path):
    store = LifelineSessionStore(path=tmp_path / "lifeline.json")
    store.observe(guidance_payload())

    store.observe(healthy_payload())
    store.observe(healthy_payload())
    payload = store.observe(healthy_payload())
    session = payload["lifeline"]["sessions"][0]

    assert session["status"] == "completed"
    assert session["healthy_observations"] == 3
    assert session["last_session"]["phase"] == "complete"
    assert session["last_session"]["recovery_verified"] is True


def test_repeat_fault_creates_new_attempt_without_erasing_history(tmp_path):
    store = LifelineSessionStore(path=tmp_path / "lifeline.json")
    first = store.observe(guidance_payload())["lifeline"]["sessions"][0]
    first_id = first["id"]

    store.observe(healthy_payload())
    store.observe(healthy_payload())
    closed = store.observe(healthy_payload())["lifeline"]["sessions"][0]
    assert closed["id"] == first_id
    assert closed["status"] == "completed"

    repeated = store.observe(guidance_payload())
    sessions = repeated["lifeline"]["sessions"]

    assert len(sessions) == 2
    assert [item["attempt"] for item in sessions] == [1, 2]
    assert sessions[0]["id"] == first_id
    assert sessions[0]["status"] == "completed"
    assert sessions[1]["status"] == "active"
    assert sessions[1]["id"].endswith(":attempt-2")
    assert sessions[1]["id"] != first_id
    assert sessions[1]["fault_key"] == sessions[0]["fault_key"]


def test_degraded_observation_resets_healthy_verification_count(tmp_path):
    store = LifelineSessionStore(path=tmp_path / "lifeline.json")
    store.observe(guidance_payload())
    store.observe(healthy_payload())
    store.observe(healthy_payload())

    payload = store.observe(
        {
            "storage": {
                "pools": [{"name": "HDDs", "health": "DEGRADED"}],
                "zfs_activity": {"resilver_running": False},
            },
            "operator_guidance": [],
        }
    )

    assert payload["lifeline"]["sessions"][0]["healthy_observations"] == 0


def test_ledger_file_contains_metadata_not_raw_disk_content(tmp_path):
    path = tmp_path / "lifeline.json"
    store = LifelineSessionStore(path=path)
    store.observe(guidance_payload())

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert "sessions" in payload
    assert "subprocess" not in path.read_text(encoding="utf-8")
