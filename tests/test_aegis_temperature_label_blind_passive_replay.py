from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_label_blind_passive_replay import (
    DETECTOR_ID,
    detector_contract,
)
from truepanel.holodeck.aegis_temperature_label_blind_passive_replay import (
    run_temperature_label_blind_passive_replay_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_view_holds_before_confirmed_recording_intake():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_label_blind_passive_replay"
    ]
    assert result["status"] == "HOLD"
    assert result["replay_receipt_written"] is False
    assert result["label_blind"] is False
    assert result["labels_present"] is False
    assert result["passive_replay_performed"] is False
    assert result["live_capture_performed"] is False
    assert result["field_validated"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def test_detector_contract_is_fixed_before_replay_and_forbids_learning():
    contract = detector_contract()
    assert contract["detector_id"] == DETECTOR_ID
    assert contract["baseline_samples"] == 12
    assert len(contract["required_evidence"]) == 5
    assert contract["labels_allowed"] is False
    assert contract["online_learning"] is False
    assert contract["threshold_tuning"] is False


def test_label_blind_replay_is_fail_closed_and_non_operational():
    report = run_temperature_label_blind_passive_replay_checkride()
    assert report["measurements"] == {
        "scenario_count": 13,
        "ready_count": 1,
        "hold_count": 12,
        "sample_count": 48,
        "baseline_sample_count": 12,
        "supporting_signal_count": 5,
        "confidence": 0.95,
        "coverage_total": 8,
        "coverage_trusted": 8,
        "coverage_gaps": 0,
        "shared_cooling_first_match_sample": 19,
        "isolated_threshold_first_match_sample": 46,
        "lead_samples": 27,
        "replay_receipt_writes": 2,
        "passive_replays_performed": 2,
        "labels_revealed": 0,
        "live_captures": 0,
        "battle_station_accesses": 0,
        "field_validations": 0,
        "candidate_acceptances": 0,
        "candidate_installations": 0,
        "deployments": 0,
        "hardware_actions": 0,
        "runtime_writes": 0,
        "unsafe_ready_count": 0,
        "fixture_private_keys_created": 1,
        "fixture_private_keys_retained": 0,
    }


def test_preserved_label_blind_replay_evidence_matches_rehearsal():
    preserved = json.loads(
        (
            ROOT / "docs/evidence/aegis-temperature-label-blind-passive-replay-v1.json"
        ).read_text()
    )
    assert preserved == run_temperature_label_blind_passive_replay_checkride()


def test_mobile_view_exposes_hypothesis_evidence_lead_and_authority_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Label-Blind Passive Replay" in source
    assert "Exact intake · independent replay · evidence receipt" in source
    assert "Probable cause:" in source
    assert "Shared-cooling match:" in source
    assert "Evidence signals:" in source
    assert "This receipt is diagnosis evidence only" in source
    assert "@media(max-width:760px)" in source
