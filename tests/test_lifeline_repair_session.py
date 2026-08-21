from truepanel.lifeline import evaluate_drive_repair


def evidence(**overrides):
    payload = {
        "pool": "HDDs",
        "pool_state": "DEGRADED",
        "vdev": "raidz1-0",
        "vdev_topology": "RAIDZ1",
        "remaining_redundancy": 0,
        "device": "sdc",
        "bay": 3,
        "zfs_state": "FAULTED",
        "capacity_bytes": 8_000_000_000_000,
        "resilver_state": {
            "resilver_running": False,
        },
    }
    payload.update(overrides)
    return payload


def candidate(**overrides):
    payload = {
        "device": "sdh",
        "model": "ST8000NE001",
        "capacity_bytes": 8_000_000_000_000,
        "member_of_pool": False,
        "contains_preserved_data": False,
        "ambiguous": False,
    }
    payload.update(overrides)
    return payload


def gate(session, code):
    return next(item for item in session.gates if item.code == code)


def test_incomplete_evidence_stays_in_diagnosis():
    session = evaluate_drive_repair(
        evidence(vdev_topology=None, remaining_redundancy=None),
    )

    assert session.phase == "diagnose"
    assert session.can_begin_physical_service is False
    assert "redundancy" in session.blocked_by


def test_logical_member_without_bay_stays_in_identify():
    session = evaluate_drive_repair(evidence(bay=None))

    assert session.phase == "identify"
    assert session.can_identify_bay is False
    assert gate(session, "physical_identity").satisfied is False


def test_verified_bay_still_requires_procedure_and_backup():
    session = evaluate_drive_repair(evidence())

    assert session.phase == "prepare"
    assert session.can_identify_bay is True
    assert session.can_begin_physical_service is False
    assert "service_procedure" in session.blocked_by
    assert "backup_acknowledgement" in session.blocked_by


def test_service_ready_requires_all_physical_prerequisites():
    session = evaluate_drive_repair(
        evidence(),
        service_procedure_verified=True,
        backup_acknowledged=True,
    )

    assert session.phase == "service_ready"
    assert session.can_begin_physical_service is True
    assert session.can_execute_replacement is False


def test_undersized_replacement_is_rejected():
    session = evaluate_drive_repair(
        evidence(),
        service_procedure_verified=True,
        backup_acknowledged=True,
        replacement_candidate=candidate(capacity_bytes=7_000_000_000_000),
    )

    assert session.phase == "validate_replacement"
    assert session.replacement.valid is False
    assert "replacement_capacity_too_small" in session.replacement.reasons
    assert session.can_execute_replacement is False


def test_candidate_with_preserved_data_is_rejected():
    session = evaluate_drive_repair(
        evidence(),
        service_procedure_verified=True,
        backup_acknowledged=True,
        replacement_candidate=candidate(contains_preserved_data=True),
    )

    assert session.phase == "validate_replacement"
    assert "replacement_contains_preserved_data" in session.replacement.reasons


def test_valid_replacement_reaches_confirmation_boundary():
    session = evaluate_drive_repair(
        evidence(),
        service_procedure_verified=True,
        backup_acknowledged=True,
        replacement_candidate=candidate(),
    )

    assert session.phase == "replacement_ready"
    assert session.replacement.valid is True
    assert session.can_prepare_replacement is True
    assert session.write_preconditions_complete is False
    assert session.can_execute_replacement is False
    assert "replacement_confirmation" in session.blocked_by


def test_full_planning_contract_still_has_no_write_authority():
    session = evaluate_drive_repair(
        evidence(),
        service_procedure_verified=True,
        backup_acknowledged=True,
        replacement_candidate=candidate(),
        replacement_operation_confirmed=True,
    )

    assert session.phase == "replacement_ready"
    assert session.write_preconditions_complete is True
    assert session.can_execute_replacement is False
    assert any(
        "execution authority is intentionally absent" in warning
        for warning in session.warnings
    )


def test_active_resilver_overrides_service_planning():
    session = evaluate_drive_repair(
        evidence(
            resilver_state={
                "resilver_running": True,
                "percent": 31,
            },
        ),
        service_procedure_verified=True,
        backup_acknowledged=True,
        replacement_candidate=candidate(),
        replacement_operation_confirmed=True,
    )

    assert session.phase == "monitor_recovery"
    assert session.recovery_in_progress is True
    assert session.write_preconditions_complete is False
    assert session.can_begin_physical_service is False
    assert session.can_execute_replacement is False
    assert any("Do not remove" in warning for warning in session.warnings)


def test_online_pool_enters_verification_before_close():
    session = evaluate_drive_repair(
        evidence(
            pool_state="ONLINE",
            replacement_zfs_state="ONLINE",
            zfs_state="FAULTED",
        )
    )

    assert session.phase == "verify"
    assert session.recovery_verified is False


def test_explicit_verified_recovery_closes_repair():
    session = evaluate_drive_repair(
        evidence(
            pool_state="ONLINE",
            replacement_zfs_state="ONLINE",
            recovery_verified=True,
        )
    )

    assert session.phase == "complete"
    assert session.recovery_verified is True


def test_phase_order_never_moves_backward_for_normal_drive_repair():
    diagnose = evaluate_drive_repair(
        evidence(vdev_topology=None, remaining_redundancy=None)
    )
    identify = evaluate_drive_repair(evidence(bay=None))
    prepare = evaluate_drive_repair(evidence())
    service = evaluate_drive_repair(
        evidence(),
        service_procedure_verified=True,
        backup_acknowledged=True,
    )
    replacement = evaluate_drive_repair(
        evidence(),
        service_procedure_verified=True,
        backup_acknowledged=True,
        replacement_candidate=candidate(),
    )

    indexes = [
        diagnose.phase_index,
        identify.phase_index,
        prepare.phase_index,
        service.phase_index,
        replacement.phase_index,
    ]
    assert indexes == sorted(indexes)


def test_zero_remaining_redundancy_is_explicitly_warned():
    session = evaluate_drive_repair(evidence(remaining_redundancy=0))

    assert any(
        "No additional member failure" in warning
        for warning in session.warnings
    )


def test_payload_is_json_friendly_contract():
    payload = evaluate_drive_repair(evidence()).to_payload()

    assert payload["kind"] == "drive_replacement"
    assert payload["target"]["bay"] == 3
    assert payload["gates"][0]["code"] == "member_identity"
    assert payload["replacement"]["detected"] is False
    assert payload["can_execute_replacement"] is False
