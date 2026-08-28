from __future__ import annotations

from truepanel.guidance.checklist import (
    checklist_for_guidance,
    checklists_for_guidance,
)


def _disk_card(*, blocked_by: list[str], resilver_running: bool = False) -> dict:
    return {
        "code": "storage.disk_faulted",
        "title": "Pool member faulted",
        "severity": "warning",
        "immediate_actions": [
            {
                "title": "Protect remaining redundancy",
                "detail": "Do not remove another member.",
                "risk": "safe",
                "requires_shutdown": False,
                "destructive": False,
            }
        ],
        "diagnosis": [],
        "remediation": [
            {
                "title": "Start the TrueNAS replacement",
                "detail": "Begin the replacement workflow.",
                "risk": "destructive",
                "requires_shutdown": False,
                "destructive": True,
            }
        ],
        "verification": [
            {
                "title": "Confirm redundancy restored",
                "detail": "Require the pool to return ONLINE.",
                "risk": "safe",
                "requires_shutdown": False,
                "destructive": False,
            }
        ],
        "runtime": {
            "active": True,
            "phase": "prepare_repair",
            "evidence": {
                "pool": "HDDs",
                "vdev": "raidz1-0",
                "member_id": "member-4",
                "bay": 4,
                "capacity_bytes": 8_000_000_000_000,
                "resilver_state": {"resilver_running": resilver_running},
            },
            "action_gate": {
                "safe_checks": True,
                "physical_service_ready": False,
                "destructive_actions_ready": False,
                "blocked_by": blocked_by,
            },
        },
    }


def test_disk_checklist_marks_only_runtime_evidence_as_verified() -> None:
    checklist = checklist_for_guidance(
        _disk_card(
            blocked_by=[
                "chassis_service_procedure_not_verified",
                "backup_acknowledgement_required",
                "replacement_candidate_not_validated",
            ]
        )
    )

    states = {item["key"]: item["state"] for item in checklist["preflight"]}

    assert checklist["read_only"] is True
    assert checklist["status"] == "hold"
    assert states["member_identity"] == "verified"
    assert states["physical_bay"] == "verified"
    assert states["service_procedure"] == "hold"
    assert states["backup_acknowledgement"] == "hold"
    assert states["replacement_candidate"] == "hold"


def test_destructive_repair_step_stays_blocked_without_authority() -> None:
    checklist = checklist_for_guidance(_disk_card(blocked_by=[]))
    remediation = next(
        section
        for section in checklist["sections"]
        if section["key"] == "remediation"
    )
    replace_step = remediation["steps"][0]

    assert checklist["status"] == "ready_with_gates"
    assert replace_step["state"] == "blocked"
    assert replace_step["blocked_by"] == [
        "destructive_action_authority_required"
    ]
    assert checklist["action_gate"]["destructive_actions_ready"] is False


def test_resilver_in_progress_becomes_monitor_hold() -> None:
    checklist = checklist_for_guidance(
        _disk_card(blocked_by=[], resilver_running=True)
    )
    recovery = next(
        item
        for item in checklist["preflight"]
        if item["key"] == "recovery_activity"
    )

    assert recovery["state"] == "monitor"
    assert recovery["blocked_by"] == ["resilver_in_progress"]
    assert checklist["status"] == "hold"


def test_generic_guidance_compiles_without_claiming_human_completion() -> None:
    card = {
        "code": "network.link_down",
        "title": "Network interface link lost",
        "severity": "caution",
        "immediate_actions": [
            {
                "title": "Check cable",
                "detail": "Inspect the cable path.",
                "risk": "safe",
                "requires_shutdown": False,
                "destructive": False,
            }
        ],
        "diagnosis": [],
        "remediation": [],
        "verification": [],
        "runtime": {
            "active": True,
            "phase": "diagnose",
            "evidence": {"interface": "enp116s0", "link_up": False},
            "action_gate": {
                "safe_checks": True,
                "physical_service_ready": False,
                "destructive_actions_ready": False,
                "blocked_by": ["cable_path_not_verified"],
            },
        },
    }

    checklist = checklist_for_guidance(card)

    assert checklist["preflight"] == []
    assert checklist["sections"][0]["steps"][0]["state"] == "pending"
    assert checklist["progress"] == {"verified": 0, "total": 0}


def test_collection_ignores_inactive_cards() -> None:
    active = _disk_card(blocked_by=[])
    inactive = _disk_card(blocked_by=[])
    inactive["runtime"]["active"] = False

    checklists = checklists_for_guidance([active, inactive])

    assert len(checklists) == 1
    assert checklists[0]["code"] == "storage.disk_faulted"
