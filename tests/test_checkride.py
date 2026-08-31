from pathlib import Path

from truepanel.aegis import (
    AegisReliabilityEngine,
    compose_storage_checkride,
    run_storage_recovery_rehearsals,
)

ROOT = Path(__file__).resolve().parents[1]


def storage_incident(*, complete=True):
    evidence = {
        "pool": "HDDs",
        "vdev": "raidz1-0",
        "bay": 3 if complete else None,
        "device": "sda",
        "model": "ST8000NE001-2M71",
        "serial_last4": "MW6D" if complete else None,
        "zfs_state": "ONLINE",
        "vdev_topology": "RAIDZ1",
        "remaining_redundancy": 1,
        "reallocated": 16120,
        "pending": 1608,
        "offline_uncorrectable": 1608,
        "reported_uncorrect": 905,
    }
    return {
        "incident_id": "recovery:b128b6846467dd1e",
        "supporting_signals": [
            {
                "source": "verified_detector",
                "signal": "storage.smart_warning",
                "state": "diagnosing",
                "evidence": evidence,
            }
        ],
    }


def guidance_card():
    incident = storage_incident()
    evidence = incident["supporting_signals"][0]["evidence"]
    return {
        "code": "storage.smart_warning",
        "title": "Critical drive-health evidence detected",
        "summary": "Raw SMART evidence indicates active media degradation.",
        "severity": "critical",
        "immediate_actions": [
            {"detail": "Confirm backup health before taking storage-repair actions."}
        ],
        "runtime": {"phase": "diagnose", "evidence": evidence},
        "recovery": {
            "incident_id": incident["incident_id"],
            "state": "diagnosing",
            "verification": {"status": "pending"},
        },
    }


def test_checkride_composes_identity_bound_advisory_plan():
    incident = storage_incident()
    plan = compose_storage_checkride(
        {"storage": {"zfs_activity": {"resilver_running": False}}},
        incident,
    )

    assert plan is not None
    assert plan["incident_id"] == incident["incident_id"]
    assert plan["presentation_scope"] == "active_incident"
    assert plan["applies_to_active_incident"] is True
    assert plan["identity"]["bay"] == 3
    assert plan["identity"]["serial_last4"] == "MW6D"
    assert plan["identity"]["verified_from_passive_evidence"] is True
    assert plan["topology"]["remaining_redundancy"] == 1
    assert plan["control_authority"] is False
    assert plan["field_validated"] is False
    assert plan["action_gate"]["physical_service_ready"] is False
    assert "replacement_candidate_not_verified" in plan["action_gate"]["blocked_by"]
    assert plan["verification_signature"]["status"] == "awaiting_external_repair"
    assert len(plan["evidence_sha256"]) == 64


def test_checkride_fails_closed_when_identity_or_topology_is_unknown():
    incident = storage_incident(complete=False)
    incident["supporting_signals"][0]["evidence"].pop("remaining_redundancy")
    plan = compose_storage_checkride({}, incident)

    assert plan is not None
    assert plan["identity"]["missing"] == ["bay", "serial_last4"]
    assert "physical_and_logical_identity_incomplete" in plan["action_gate"]["blocked_by"]
    assert "redundancy_context_incomplete" in plan["action_gate"]["blocked_by"]
    assert plan["topology"]["remaining_redundancy"] is None


def test_checkride_rehearses_success_and_abort_branches_without_hardware():
    rehearsals = run_storage_recovery_rehearsals()

    assert len(rehearsals) == 6
    assert all(item["hardware_isolated"] is True for item in rehearsals)
    assert {item["outcome"] for item in rehearsals} >= {
        "proceed_to_operator_review",
        "abort",
        "hold",
        "observe",
        "hold_and_escalate",
    }


def test_aegis_binds_checkride_to_exact_live_storage_incident():
    payload = {
        "timestamp": 1,
        "operator_guidance": [guidance_card()],
        "storage": {"zfs_activity": {"resilver_running": False}},
    }
    reliability = AegisReliabilityEngine().observe(payload)
    flight = reliability["flight_director"]

    assert reliability["active_incident"]["incident_id"] == flight["incident_id"]
    assert flight["project"] == "CHECKRIDE"
    assert flight["domain"] == "storage"
    assert flight["safest_action"].startswith("Keep bay 3")


def test_mission_control_exposes_storage_plan_without_hiding_abort_conditions():
    reliability_source = (
        ROOT / "truepanel/web/static/reliability-view.js"
    ).read_text()
    cockpit_source = (ROOT / "truepanel/web/static/glass-cockpit.js").read_text()

    for label in (
        "Project CHECKRIDE",
        "PHYSICAL SERVICE HOLD",
        "Abort conditions",
        "HoloDeck Recovery Rehearsals",
        "Keep the drive installed",
    ):
        assert label in reliability_source
    assert 'flight?.incident_id===incident?.incident_id' in cockpit_source
    assert "flight?.safest_action" in cockpit_source
    assert "setInterval" not in reliability_source
    assert "setInterval" not in cockpit_source
