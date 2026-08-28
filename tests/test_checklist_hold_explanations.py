from __future__ import annotations

from truepanel.guidance.checklist import checklist_for_guidance


def _card(*, replacement_valid: bool = False, backup: bool = False) -> dict:
    replacement = {
        "detected": replacement_valid,
        "valid": replacement_valid,
        "device": "sdb" if replacement_valid else None,
        "model": "ST8000NE001-2M7101" if replacement_valid else None,
        "capacity_bytes": 8_001_563_222_016 if replacement_valid else None,
        "minimum_capacity_bytes": 8_001_563_222_016,
        "reasons": [] if replacement_valid else ["replacement_not_detected"],
    }
    gates = [
        {
            "code": "member_identity",
            "title": "At-risk member identified",
            "satisfied": True,
            "detail": "Pool, VDEV, member identity, and SMART evidence agree.",
            "risk": "safe",
        },
        {
            "code": "redundancy",
            "title": "VDEV redundancy understood",
            "satisfied": True,
            "detail": "Topology and remaining fault tolerance are known.",
            "risk": "safe",
        },
        {
            "code": "physical_identity",
            "title": "Physical bay independently verified",
            "satisfied": True,
            "detail": "Bay identity is proven.",
            "risk": "safe",
        },
        {
            "code": "service_procedure",
            "title": "Chassis service procedure verified",
            "satisfied": True,
            "detail": "The chassis procedure is verified.",
            "risk": "caution",
        },
        {
            "code": "backup_acknowledgement",
            "title": "Backup state acknowledged",
            "satisfied": backup,
            "detail": "Backup state must be acknowledged.",
            "risk": "caution",
        },
        {
            "code": "replacement_candidate",
            "title": "Replacement candidate validated",
            "satisfied": replacement_valid,
            "detail": "Replacement media must satisfy validation.",
            "risk": "destructive",
        },
        {
            "code": "replacement_confirmation",
            "title": "Replacement operation explicitly confirmed",
            "satisfied": False,
            "detail": "Exact devices require guarded confirmation.",
            "risk": "destructive",
        },
    ]
    return {
        "code": "storage.smart_warning",
        "title": "Critical drive-health evidence detected",
        "severity": "critical",
        "summary": "Critical SMART evidence requires guided recovery.",
        "runtime": {
            "active": True,
            "phase": "prepare_repair",
            "evidence": {
                "pool": "HDDs",
                "vdev": "raidz1-0",
                "bay": 3,
                "device": "sda",
            },
        },
        "repair_session": {
            "phase": "prepare",
            "phase_index": 3,
            "phase_count": 9,
            "title": "Guided pre-failure drive recovery",
            "summary": "The at-risk bay is known.",
            "target": {
                "pool": "HDDs",
                "vdev": "raidz1-0",
                "member_id": "/dev/sda1",
                "bay": 3,
                "device": "sda",
            },
            "gates": gates,
            "replacement": replacement,
            "can_identify_bay": True,
            "can_begin_physical_service": backup,
            "can_prepare_replacement": backup and replacement_valid,
            "write_preconditions_complete": False,
            "can_execute_replacement": False,
            "blocked_by": [
                gate["code"]
                for gate in gates
                if gate["satisfied"] is not True
            ],
            "warnings": [],
        },
    }


def test_live_four_of_seven_state_explains_current_holds_and_authority() -> None:
    checklist = checklist_for_guidance(_card())
    preflight = {item["key"]: item for item in checklist["preflight"]}

    assert checklist["status"] == "hold"
    assert checklist["progress"] == {
        "verified": 4,
        "total": 7,
        "remaining": 3,
    }
    assert checklist["hold"]["remaining"] == 3
    assert checklist["hold"]["current"] == 2
    assert checklist["hold"]["authority_boundaries"] == 1
    assert checklist["hold"]["next_gate"]["key"] == "backup_acknowledgement"

    backup = preflight["backup_acknowledgement"]
    assert backup["state"] == "hold"
    assert backup["blocker_kind"] == "operator_checkpoint"
    assert "guarded backup-state acknowledgement" in backup["current_condition"]
    assert "Clear condition:" in backup["detail"]

    replacement = preflight["replacement_candidate"]
    assert replacement["state"] == "hold"
    assert replacement["blocker_kind"] == "replacement_media"
    assert replacement["current_condition"] == (
        "No replacement candidate is currently detected."
    )

    authority = preflight["replacement_confirmation"]
    assert authority["state"] == "blocked"
    assert authority["authority_boundary"] is True
    assert authority["blocker_kind"] == "authority_boundary"
    assert "never grants storage execution authority" in authority["clears_when"]

    assert "HOLD: 3 unresolved recovery gates remain." in checklist["summary"]
    assert "Current blockers: Backup state acknowledged;" in checklist["summary"]
    assert "Authority boundary:" in checklist["summary"]
    assert "Next safe checkpoint: Backup state acknowledged." in checklist["summary"]


def test_only_future_confirmation_remaining_becomes_authority_hold() -> None:
    checklist = checklist_for_guidance(
        _card(replacement_valid=True, backup=True)
    )

    assert checklist["status"] == "authority_hold"
    assert checklist["progress"] == {
        "verified": 6,
        "total": 7,
        "remaining": 1,
    }
    assert checklist["hold"]["current"] == 0
    assert checklist["hold"]["authority_boundaries"] == 1
    assert checklist["hold"]["next_gate"]["key"] == "replacement_confirmation"
    assert "Remaining authority checkpoint:" in checklist["summary"]
    assert checklist["capabilities"]["can_execute_replacement"] is False


def test_clearance_metadata_never_creates_manual_completion_authority() -> None:
    checklist = checklist_for_guidance(_card())

    encoded = repr(checklist)
    assert "Mark PASS" not in encoded
    assert "Resolve fault" not in encoded
    assert "can_execute_replacement': False" in encoded
