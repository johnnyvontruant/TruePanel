from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.holodeck.aegis_temperature_blinded_cohort_manifest import (
    run_temperature_blinded_cohort_manifest_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_view_waits_for_inventory_without_claiming_authority():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_blinded_cohort_manifest"
    ]
    assert result["status"] == "ACTION_REQUIRED_BLINDED_COHORT_PLAN"
    assert result["statistical_contract_ready"] is True
    assert result["plan_present"] is False
    assert result["manifest_present"] is False
    assert result["ready_for_authenticated_label_join"] is False
    assert result["eligible_for_independent_scoring"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def test_two_phase_freeze_is_complete_order_independent_and_label_blind():
    report = run_temperature_blinded_cohort_manifest_checkride()
    assert report["measurements"] == {
        "scenario_count": 12,
        "frozen_count": 2,
        "hold_count": 10,
        "unsafe_ready_count": 0,
        "planned_case_count": 440,
        "result_count": 440,
        "system_profile_count": 2,
        "workload_class_count": 4,
        "order_independent_manifest_identity": True,
        "planned_omissions_accepted": 0,
        "unplanned_results_accepted": 0,
        "duplicate_results_accepted": 0,
        "labels_accepted": 0,
        "scores_accepted": 0,
        "field_validations": 0,
        "candidate_acceptances": 0,
        "candidate_installations": 0,
        "deployments": 0,
        "hardware_actions": 0,
        "runtime_writes": 0,
    }


def test_preserved_evidence_matches_the_deterministic_checkride():
    report = run_temperature_blinded_cohort_manifest_checkride()
    preserved = json.loads(
        (
            ROOT / "docs/evidence/aegis-temperature-blinded-cohort-manifest-v1.json"
        ).read_text()
    )
    assert preserved == report


def test_mobile_view_exposes_the_two_phase_freeze_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Blinded Cohort Freeze" in source
    assert "Inventory first · predictions second · labels last" in source
    assert (
        "Missing, extra, duplicate, drifted, relabeled, or post-freeze-edited members remain HOLD"
        in source
    )
    assert "@media(max-width:760px)" in source
