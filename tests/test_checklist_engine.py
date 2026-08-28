from __future__ import annotations

from truepanel.guidance.checklist import (
    checklist_for_guidance,
    checklists_for_guidance,
)


def _disk_card(*, phase: str = "prepare", all_gates: bool = False) -> dict:
    gates = [
        {
            "code": "member_identity",
            "title": "Faulted member identified",
            "detail": "Pool, VDEV, member, and state agree.",
            "risk": "safe",
            "satisfied": True,
        },
        {
            "code": "physical_identity",
            "title": "Physical bay independently verified",
            "detail": "Bay identity is proven.",
            "risk": "safe",
            "satisfied": True,
        },
        {
            "code": "service_procedure",
            "title": "Chassis service procedure verified",
            "detail": "Model-specific service procedure is verified.",
            "risk": "caution",
            "satisfied": all_gates,
        },
        {
            "code": "backup_acknowledgement",
            "title": "Backup state acknowledged",
            "detail": "Operator acknowledged backup state.",
            "risk": "caution",
            "satisfied": all_gates,
        },
        {
            "code": "replacement_candidate",
            "title": "Replacement candidate validated",
            "detail": "Replacement media satisfies the validation contract.",
            "risk": "destructive",
            "satisfied": all_gates,
        },
        {
            "code": "replacement_confirmation",
            "title": "Replacement operation explicitly confirmed",
            "detail": "Explicit confirmation is tied to exact devices.",
            "risk": "destructive",
            "satisfied": all_gates,
        },
    ]
    return {
        "code": "storage.disk_faulted",
        "title": "Pool member faulted",
        "summary": "A member requires guided recovery.",
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
        "verification": [],
        "runtime": {
            "active": True,
            "phase": "prepare_repair",
            "evidence": {"pool": "HDDs", "bay": 4},
        },
        "repair_session": {
            "phase": phase,
            "phase_index": 3,
            "phase_count": 9,
            "title": "Guided drive recovery",
            "summary": "Verify service prerequisites before physical service.",
            "target": {
                "pool": "HDDs",
                "vdev": "raidz1-0",
                "member_id": "/dev/sdc1",
                "bay": 4,
                "device": "sdc",
            },
            "gates": gates,
            "can_identify_bay": True,
            "can_begin_physical_service": all_gates,
            "can_prepare_replacement": all_gates,
            "write_preconditions_complete": all_gates,
            "can_execute_replacement": False,
            "blocked_by": (
                []
                if all_gates
                else [
                    "service_procedure",
                    "backup_acknowledgement",
                    "replacement_candidate",
                    "replacement_confirmation",
                ]
            ),
            "warnings": [
                "No additional member failure can be tolerated in the affected VDEV."
            ],
        },
    }


def test_checklist_uses_lifeline_gates_as_preflight_truth() -> None:
    checklist = checklist_for_guidance(_disk_card())
    states = {item["key"]: item["state"] for item in checklist["preflight"]}

    assert checklist["read_only"] is True
    assert checklist["status"] == "hold"
    assert checklist["recovery_kind"] == "drive_replacement"
    assert states["member_identity"] == "verified"
    assert states["physical_identity"] == "verified"
    assert states["service_procedure"] == "hold"
    assert states["replacement_candidate"] == "hold"


def test_smart_prefailure_with_lifeline_session_is_drive_recovery() -> None:
    card = _disk_card()
    card["code"] = "storage.smart_warning"
    card["title"] = "Critical drive-health evidence detected"
    card["runtime"]["phase"] = "diagnose"
    card["runtime"]["evidence"] = {
        "pool": "HDDs",
        "vdev": "raidz1-0",
        "bay": 3,
        "device": "sda",
        "pending": 1608,
        "offline_uncorrectable": 1608,
    }
    card["repair_session"]["target"] = {
        "pool": "HDDs",
        "vdev": "raidz1-0",
        "member_id": "/dev/sda1",
        "bay": 3,
        "device": "sda",
        "trigger": "critical_smart_prefailure",
    }

    checklist = checklist_for_guidance(card)

    assert checklist["code"] == "storage.smart_warning"
    assert checklist["recovery_kind"] == "drive_replacement"
    assert checklist["target"]["bay"] == 3
    assert checklist["target"]["device"] == "sda"
    assert checklist["capabilities"]["can_identify_bay"] is True
    assert checklist["progress"]["total"] == 6


def test_human_procedure_text_is_never_auto_completed() -> None:
    checklist = checklist_for_guidance(_disk_card(all_gates=True))
    remediation = next(
        section
        for section in checklist["sections"]
        if section["key"] == "remediation"
    )

    assert remediation["steps"][0]["state"] == "pending"
    assert remediation["steps"][0]["destructive"] is True


def test_write_preconditions_stop_at_authority_hold() -> None:
    checklist = checklist_for_guidance(_disk_card(all_gates=True))

    assert checklist["status"] == "authority_hold"
    assert checklist["capabilities"]["write_preconditions_complete"] is True
    assert checklist["capabilities"]["can_execute_replacement"] is False


def test_resilver_phase_becomes_monitor_state() -> None:
    checklist = checklist_for_guidance(
        _disk_card(phase="monitor_recovery", all_gates=True)
    )

    assert checklist["status"] == "monitor"
    assert checklist["phase"] == "monitor_recovery"


def test_generic_guidance_remains_a_read_only_pending_procedure() -> None:
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
        },
    }

    checklist = checklist_for_guidance(card)

    assert checklist["preflight"] == []
    assert checklist["sections"][0]["steps"][0]["state"] == "pending"
    assert checklist["progress"] == {"verified": 0, "total": 0}
    assert checklist["recovery_kind"] == "generic"
    assert checklist["read_only"] is True


def test_collection_ignores_inactive_cards() -> None:
    active = _disk_card()
    inactive = _disk_card()
    inactive["runtime"]["active"] = False

    checklists = checklists_for_guidance([active, inactive])

    assert len(checklists) == 1
    assert checklists[0]["code"] == "storage.disk_faulted"
