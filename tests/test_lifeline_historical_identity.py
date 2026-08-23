from truepanel.lifeline import LifelineSessionStore, evaluate_drive_repair


MEMBER_ID = "15571478626791065431"
HISTORICAL_PATH = (
    "/dev/disk/by-partuuid/"
    "389d5fd4-8899-434f-b171-ef29d8937033"
)


def missing_evidence(**overrides):
    payload = {
        "pool": "HDDs",
        "pool_state": "DEGRADED",
        "vdev": "raidz1-0",
        "vdev_topology": "RAIDZ1",
        "remaining_redundancy": 0,
        "member_id": MEMBER_ID,
        "historical_path": HISTORICAL_PATH,
        "device": None,
        "bay": None,
        "zfs_state": "UNAVAIL",
        "capacity_bytes": None,
        "resilver_state": {
            "resilver_running": False,
        },
    }
    payload.update(overrides)
    return payload


def guidance_payload():
    evidence = missing_evidence()
    return {
        "storage": {
            "pools": [{"name": "HDDs", "health": "DEGRADED"}],
            "zfs_activity": {
                "scrub_running": False,
                "resilver_running": False,
            },
        },
        "operator_guidance": [
            {
                "code": "storage.disk_faulted",
                "runtime": {
                    "evidence": evidence,
                },
            }
        ],
    }


def gate(session, code):
    return next(item for item in session.gates if item.code == code)


def test_removed_member_can_use_explicit_verified_historical_bay():
    session = evaluate_drive_repair(
        missing_evidence(
            bay=3,
            physical_identity_source="historical_verified",
            physical_identity_serial_last4="MW6D",
        ),
        bay_identity_verified=True,
    )

    assert session.phase == "prepare"
    assert gate(session, "physical_identity").satisfied is True
    assert session.can_identify_bay is True
    assert session.target["device"] is None
    assert session.target["bay"] == 3
    assert session.target["physical_identity_source"] == "historical_verified"
    assert session.target["physical_identity_serial_last4"] == "MW6D"
    assert session.can_execute_replacement is False


def test_historical_bay_without_explicit_verification_stays_locked():
    session = evaluate_drive_repair(
        missing_evidence(
            bay=3,
            physical_identity_source="historical_verified",
            physical_identity_serial_last4="MW6D",
        ),
    )

    assert session.phase == "identify"
    assert gate(session, "physical_identity").satisfied is False
    assert session.can_identify_bay is False


def test_historical_bay_without_serial_proof_stays_locked():
    session = evaluate_drive_repair(
        missing_evidence(
            bay=3,
            physical_identity_source="historical_verified",
        ),
        bay_identity_verified=True,
    )

    assert session.phase == "identify"
    assert gate(session, "physical_identity").satisfied is False
    assert session.can_identify_bay is False


def test_store_rejects_historical_identity_for_wrong_member(tmp_path):
    store = LifelineSessionStore(path=tmp_path / "lifeline.json")
    observed = store.observe(guidance_payload())
    session_id = observed["lifeline"]["sessions"][0]["id"]

    try:
        store.set_historical_physical_identity(
            session_id,
            member_id="wrong-member",
            bay=3,
            serial_last4="MW6D",
            source="archived commissioned identity record",
        )
    except ValueError as error:
        assert "does not match" in str(error)
    else:
        raise AssertionError("mismatched historical member was accepted")


def test_store_historical_identity_advances_planning_without_faking_device(tmp_path):
    path = tmp_path / "lifeline.json"
    store = LifelineSessionStore(path=path)
    observed = store.observe(guidance_payload())
    session_id = observed["lifeline"]["sessions"][0]["id"]

    original_before = observed["lifeline"]["sessions"][0]["original_fault"]
    assert original_before["device"] is None
    assert original_before["bay"] is None

    store.set_historical_physical_identity(
        session_id,
        member_id=MEMBER_ID,
        bay=3,
        serial_last4="MW6D",
        source="BattleStation 2026-07-24 archived identity diagnostic",
    )

    observed = store.observe(guidance_payload())
    session = observed["lifeline"]["sessions"][0]
    repair = session["last_session"]

    assert session["original_fault"] == original_before
    assert session["context"]["physical_identity"] == {
        "verified": True,
        "kind": "historical_verified",
        "member_id": MEMBER_ID,
        "bay": 3,
        "serial_last4": "MW6D",
        "source": "BattleStation 2026-07-24 archived identity diagnostic",
    }
    assert repair["phase"] == "prepare"
    assert repair["target"]["device"] is None
    assert repair["target"]["bay"] == 3
    assert repair["target"]["physical_identity_source"] == "historical_verified"
    assert repair["can_identify_bay"] is True
    assert repair["can_begin_physical_service"] is False
    assert repair["can_execute_replacement"] is False


def test_historical_identity_survives_store_restart(tmp_path):
    path = tmp_path / "lifeline.json"
    first = LifelineSessionStore(path=path)
    observed = first.observe(guidance_payload())
    session_id = observed["lifeline"]["sessions"][0]["id"]

    first.set_historical_physical_identity(
        session_id,
        member_id=MEMBER_ID,
        bay=3,
        serial_last4="MW6D",
        source="commissioned historical identity ledger",
    )

    second = LifelineSessionStore(path=path)
    observed = second.observe(guidance_payload())
    session = observed["lifeline"]["sessions"][0]

    assert session["id"] == session_id
    assert session["context"]["physical_identity"]["verified"] is True
    assert session["last_session"]["phase"] == "prepare"
    assert session["last_session"]["target"]["bay"] == 3
    assert session["last_session"]["target"]["device"] is None
    assert session["last_session"]["can_execute_replacement"] is False
