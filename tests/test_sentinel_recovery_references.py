from copy import deepcopy

from truepanel.sentinel import (
    attach_recovery_references,
    recovery_references_for_source,
)


def _guidance(device="/dev/sdc", *, runtime_device=None, code="storage.smart_warning"):
    runtime_device = device if runtime_device is None else runtime_device
    return {
        "code": code,
        "title": "Critical drive-health evidence detected",
        "severity": "critical",
        "summary": "Inspect the failing drive evidence before replacement.",
        "runtime": {
            "active": True,
            "evidence": {"device": runtime_device, "bay": 3},
        },
        "recovery": {
            "schema_version": 1,
            "incident_id": "recovery:abc123",
            "code": code,
            "state": "diagnosing",
            "severity": "critical",
            "explanation": "Inspect the failing drive evidence before replacement.",
            "evidence": {"device": device, "bay": 3},
            "verification": {
                "strategy": "smart_and_zfs_recheck",
                "status": "pending",
            },
            "action_gate": {
                "safe_checks": True,
                "physical_service_ready": False,
                "destructive_actions_ready": False,
                "blocked_by": ["physical_bay_not_identified"],
            },
        },
    }


def test_reference_requires_exact_recovery_device_identity():
    assert recovery_references_for_source("/dev/sdc", [_guidance()]) == [
        {
            "kind": "pathfinder_guidance",
            "source_device": "/dev/sdc",
            "incident_id": "recovery:abc123",
            "code": "storage.smart_warning",
            "title": "Critical drive-health evidence detected",
            "severity": "critical",
            "explanation": "Inspect the failing drive evidence before replacement.",
            "verification": {
                "strategy": "smart_and_zfs_recheck",
                "status": "pending",
            },
            "action_gate": {
                "safe_checks": True,
                "physical_service_ready": False,
                "destructive_actions_ready": False,
                "blocked_by": ["physical_bay_not_identified"],
            },
            "authority": False,
        }
    ]


def test_reference_rejects_similar_but_different_device():
    assert recovery_references_for_source("/dev/sdc", [_guidance("/dev/sdd")]) == []


def test_reference_fails_closed_on_runtime_recovery_identity_conflict():
    card = _guidance("/dev/sdc", runtime_device="/dev/sdd")

    assert recovery_references_for_source("/dev/sdc", [card]) == []


def test_reference_does_not_match_on_bay_title_or_severity_alone():
    card = _guidance("/dev/sdd")
    card["title"] = "Bay 3 critical drive-health evidence"
    card["runtime"]["evidence"]["bay"] = 3
    card["recovery"]["evidence"]["bay"] = 3

    assert recovery_references_for_source("/dev/sdc", [card]) == []


def test_attach_marks_reference_available_without_granting_authority():
    sentinel = {
        "explanations": [
            {
                "source_device": "/dev/sdc",
                "recovery": {
                    "available": False,
                    "authority": False,
                    "reason": "Flight Director v1 has no recovery reference.",
                },
            }
        ]
    }

    attach_recovery_references(sentinel, [_guidance()])

    recovery = sentinel["explanations"][0]["recovery"]
    assert recovery["available"] is True
    assert recovery["authority"] is False
    assert len(recovery["references"]) == 1
    assert "does not grant" in recovery["reason"]
    assert "workflow_state" not in recovery["references"][0]


def test_attach_keeps_explanation_unavailable_without_proved_reference():
    sentinel = {
        "explanations": [
            {
                "source_device": "/dev/sdc",
                "recovery": {
                    "available": False,
                    "authority": False,
                },
            }
        ]
    }
    before = deepcopy(sentinel)

    attach_recovery_references(sentinel, [_guidance("/dev/sdd")])

    recovery = sentinel["explanations"][0]["recovery"]
    assert recovery["available"] is False
    assert recovery["authority"] is False
    assert recovery["references"] == []
    assert before["explanations"][0]["source_device"] == "/dev/sdc"
