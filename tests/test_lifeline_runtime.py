from truepanel.lifeline import attach_repair_sessions


def disk_guidance(**evidence_overrides):
    evidence = {
        "pool": "HDDs",
        "pool_state": "DEGRADED",
        "vdev": "raidz1-0",
        "vdev_topology": "RAIDZ1",
        "remaining_redundancy": 0,
        "bay": 3,
        "device": "sdc",
        "zfs_state": "FAULTED",
        "capacity_bytes": 8_000_000_000_000,
        "resilver_state": {"resilver_running": False},
    }
    evidence.update(evidence_overrides)
    return {
        "code": "storage.disk_faulted",
        "title": "Pool member faulted",
        "runtime": {
            "evidence": evidence,
        },
    }


def session(result):
    return result[0]["repair_session"]


def test_non_drive_guidance_is_preserved_without_session():
    item = {"code": "storage.pool_degraded", "runtime": {"evidence": {}}}

    result = attach_repair_sessions([item])

    assert result == [item]
    assert "repair_session" not in result[0]


def test_disk_guidance_gets_read_only_lifeline_session():
    result = attach_repair_sessions([disk_guidance()])

    repair = session(result)
    assert repair["kind"] == "drive_replacement"
    assert repair["phase"] == "prepare"
    assert repair["can_execute_replacement"] is False


def test_context_can_advance_planning_without_mutating_storage():
    result = attach_repair_sessions(
        [disk_guidance()],
        context={
            "service_procedure_verified": True,
            "bay_identity_verified": True,
            "acknowledgements": {"backup_state": True},
        },
    )

    repair = session(result)
    assert repair["phase"] == "service_ready"
    assert repair["can_begin_physical_service"] is True
    assert repair["can_execute_replacement"] is False


def test_single_replacement_candidate_is_validated():
    result = attach_repair_sessions(
        [disk_guidance()],
        context={
            "service_procedure_verified": True,
            "bay_identity_verified": True,
            "acknowledgements": {"backup_state": True},
            "replacement_candidates": [
                {
                    "device": "sdh",
                    "capacity_bytes": 8_000_000_000_000,
                    "member_of_pool": False,
                    "contains_preserved_data": False,
                }
            ],
        },
    )

    repair = session(result)
    assert repair["phase"] == "replacement_ready"
    assert repair["replacement"]["valid"] is True
    assert repair["can_execute_replacement"] is False


def test_multiple_unselected_candidates_are_ambiguous():
    result = attach_repair_sessions(
        [disk_guidance()],
        context={
            "service_procedure_verified": True,
            "bay_identity_verified": True,
            "acknowledgements": {"backup_state": True},
            "replacement_candidates": [
                {"device": "sdh", "capacity_bytes": 8_000_000_000_000},
                {"device": "sdi", "capacity_bytes": 8_000_000_000_000},
            ],
        },
    )

    repair = session(result)
    assert repair["phase"] == "validate_replacement"
    assert "replacement_identity_ambiguous" in repair["replacement"]["reasons"]


def test_selected_candidate_breaks_multiple_candidate_tie():
    result = attach_repair_sessions(
        [disk_guidance()],
        context={
            "service_procedure_verified": True,
            "bay_identity_verified": True,
            "acknowledgements": {"backup_state": True},
            "replacement_candidates": [
                {"device": "sdh", "capacity_bytes": 8_000_000_000_000},
                {
                    "device": "sdi",
                    "capacity_bytes": 8_000_000_000_000,
                    "selected": True,
                },
            ],
        },
    )

    repair = session(result)
    assert repair["replacement"]["device"] == "sdi"
    assert repair["replacement"]["valid"] is True


def test_resilver_forces_monitor_recovery_even_with_context():
    result = attach_repair_sessions(
        [
            disk_guidance(
                resilver_state={
                    "resilver_running": True,
                    "percent": 42,
                }
            )
        ],
        context={
            "service_procedure_verified": True,
            "acknowledgements": {
                "backup_state": True,
                "replacement_operation": True,
            },
            "replacement_candidates": [
                {"device": "sdh", "capacity_bytes": 8_000_000_000_000}
            ],
        },
    )

    repair = session(result)
    assert repair["phase"] == "monitor_recovery"
    assert repair["can_execute_replacement"] is False



def test_identity_verified_replacement_may_reuse_failed_runtime_path():
    result = attach_repair_sessions(
        [disk_guidance()],
        context={
            "service_procedure_verified": True,
            "bay_identity_verified": True,
            "acknowledgements": {"backup_state": True},
            "replacement_candidates": [
                {
                    "device": "sdc",
                    "bay": 3,
                    "capacity_bytes": 8_000_000_000_000,
                    "member_of_pool": False,
                    "contains_preserved_data": False,
                    "identity_verified_distinct": True,
                }
            ],
        },
    )

    repair = session(result)

    assert repair["replacement"]["device"] == "sdc"
    assert repair["replacement"]["valid"] is True
    assert repair["phase"] == "replacement_ready"


def test_unverified_replacement_reusing_failed_path_remains_ambiguous():
    result = attach_repair_sessions(
        [disk_guidance()],
        context={
            "service_procedure_verified": True,
            "bay_identity_verified": True,
            "acknowledgements": {"backup_state": True},
            "replacement_candidates": [
                {
                    "device": "sdc",
                    "bay": 3,
                    "capacity_bytes": 8_000_000_000_000,
                    "member_of_pool": False,
                    "contains_preserved_data": False,
                }
            ],
        },
    )

    repair = session(result)

    assert repair["replacement"]["valid"] is False
    assert "replacement_identity_ambiguous" in (
        repair["replacement"]["reasons"]
    )
