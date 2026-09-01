from copy import deepcopy
from pathlib import Path

from truepanel.aegis import (
    AegisReliabilityEngine,
    compose_storage_checkride,
    evaluate_pre_service_clearance,
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


def clearance_payload(*, now=1_000.0):
    return {
        "timestamp": now,
        "storage": {"zfs_activity": {"resilver_running": False}},
        "backup_context": {
            "independent_backup_confirmed": True,
            "restore_tested": True,
            "source": "fixture:offline-restore-report",
            "verified_at": now - 60,
        },
        "lifeline": {
            "sessions": [
                {
                    "id": "storage:fixture:attempt-1",
                    "status": "active",
                    "updated_at": now - 30,
                    "original_fault": {
                        "pool": "HDDs",
                        "vdev": "raidz1-0",
                        "bay": 3,
                        "device": "sda",
                        "serial_last4": "MW6D",
                    },
                    "context": {
                        "service_procedure_verified": True,
                        "service_profile": "qnap-tvs-x71",
                        "service_source": "QNAP TVS-x71 Series Hardware User Manual",
                        "replacement_candidates": [
                            {
                                "selected": True,
                                "device": "sdh",
                                "bay": 3,
                                "model": "ST8000NE001-2M71",
                                "serial_last4": "NEW1",
                                "capacity_bytes": 8_000_000_000_000,
                                "member_of_pool": False,
                                "contains_preserved_data": False,
                                "identity_verified_distinct": True,
                                "observed_at": now - 30,
                            }
                        ],
                    },
                    "last_session": {
                        "replacement": {
                            "valid": True,
                            "capacity_bytes": 8_000_000_000_000,
                            "minimum_capacity_bytes": 8_000_000_000_000,
                            "reasons": [],
                        }
                    },
                }
            ]
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
    assert "replacement_fit_and_identity" in plan["action_gate"]["blocked_by"]
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


def test_pre_service_clearance_requires_all_fresh_independent_evidence():
    incident = storage_incident()
    evidence = incident["supporting_signals"][0]["evidence"]
    identity = {
        field: evidence.get(field)
        for field in ("pool", "vdev", "bay", "device", "model", "serial_last4")
    }
    identity["verified_from_passive_evidence"] = True
    topology = {
        field: evidence.get(field)
        for field in ("pool", "vdev", "vdev_topology", "remaining_redundancy", "zfs_state")
    }

    receipt = evaluate_pre_service_clearance(
        clearance_payload(),
        incident_id=incident["incident_id"],
        identity=identity,
        topology=topology,
    )

    assert receipt["status"] == "READY_FOR_OPERATOR_REVIEW"
    assert receipt["operator_review_ready"] is True
    assert receipt["physical_service_authority"] is False
    assert receipt["storage_write_authority"] is False
    assert receipt["blocked_by"] == []
    assert all(gate["satisfied"] is True for gate in receipt["gates"])
    assert len(receipt["receipt_sha256"]) == 64


def test_pre_service_clearance_holds_expired_backup_and_candidate():
    incident = storage_incident()
    evidence = incident["supporting_signals"][0]["evidence"]
    payload = clearance_payload(now=2_000.0)
    payload["backup_context"]["verified_at"] = 1_000.0
    session = payload["lifeline"]["sessions"][0]
    session["updated_at"] = 1_000.0
    session["context"]["replacement_candidates"][0]["observed_at"] = 1_000.0
    identity = {
        field: evidence.get(field)
        for field in ("pool", "vdev", "bay", "device", "model", "serial_last4")
    }
    identity["verified_from_passive_evidence"] = True
    topology = {
        field: evidence.get(field)
        for field in ("pool", "vdev", "vdev_topology", "remaining_redundancy", "zfs_state")
    }

    receipt = evaluate_pre_service_clearance(
        payload,
        incident_id=incident["incident_id"],
        identity=identity,
        topology=topology,
    )

    assert receipt["status"] == "HOLD"
    assert receipt["operator_review_ready"] is False
    assert set(receipt["blocked_by"]) == {
        "backup_restore_evidence",
        "replacement_fit_and_identity",
    }


def test_checkride_embeds_clearance_but_never_grants_storage_authority():
    incident = storage_incident()
    plan = compose_storage_checkride(clearance_payload(), incident)

    assert plan is not None
    assert plan["pre_service_clearance"]["status"] == "READY_FOR_OPERATOR_REVIEW"
    assert plan["action_gate"]["operator_review_ready"] is True
    assert plan["action_gate"]["physical_service_ready"] is False
    assert plan["action_gate"]["destructive_actions_ready"] is False
    assert plan["action_gate"]["blocked_by"] == []


def test_pre_service_clearance_negative_rehearsals_fail_closed():
    cases = []

    missing_backup = clearance_payload()
    missing_backup["backup_context"]["restore_tested"] = False
    cases.append((missing_backup, storage_incident(), "backup_restore_evidence"))

    identity_mismatch = clearance_payload()
    identity_mismatch["lifeline"]["sessions"][0]["original_fault"][
        "serial_last4"
    ] = "OTHER"
    cases.append(
        (identity_mismatch, storage_incident(), "replacement_fit_and_identity")
    )

    no_margin_incident = storage_incident()
    no_margin_incident["supporting_signals"][0]["evidence"][
        "remaining_redundancy"
    ] = 0
    cases.append((clearance_payload(), no_margin_incident, "redundancy_margin"))

    invalid_candidate = clearance_payload()
    session = invalid_candidate["lifeline"]["sessions"][0]
    session["last_session"]["replacement"]["valid"] = False
    cases.append(
        (invalid_candidate, storage_incident(), "replacement_fit_and_identity")
    )

    active_resilver = clearance_payload()
    active_resilver["storage"]["zfs_activity"]["resilver_running"] = True
    cases.append((active_resilver, storage_incident(), "recovery_quiescent"))

    for payload, incident, expected_blocker in cases:
        plan = compose_storage_checkride(deepcopy(payload), deepcopy(incident))
        assert plan is not None
        receipt = plan["pre_service_clearance"]
        assert receipt["status"] == "HOLD"
        assert expected_blocker in receipt["blocked_by"]
        assert receipt["physical_service_authority"] is False
        assert receipt["storage_write_authority"] is False


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
