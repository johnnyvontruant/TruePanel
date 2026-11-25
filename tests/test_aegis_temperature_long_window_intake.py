from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_long_window_intake import (
    pending_temperature_long_window_intake,
)
from truepanel.holodeck.aegis_temperature_long_window_intake import (
    run_temperature_long_window_intake_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_long_window_intake_waits_without_claiming_authority():
    reliability = AegisReliabilityEngine().observe({"timestamp": 0.0})
    result = reliability["coverage_long_window_intake"]
    assert result["status"] == "HOLD"
    assert result["eligible_for_label_blind_replay"] is False
    assert result["capture_performed"] is False
    assert result["tailing_performed"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def test_characterized_corpus_requests_a_separate_long_window_recording():
    result = pending_temperature_long_window_intake(
        {"status": "CALIBRATION_CORPUS_CHARACTERIZED_FOR_INDEPENDENT_REVIEW"}
    )
    assert result["status"] == "ACTION_REQUIRED_LONG_WINDOW_RECORDING"
    assert result["eligible_for_label_blind_replay"] is False


def test_holodeck_long_window_intake_is_preserved_and_fails_closed():
    report = run_temperature_long_window_intake_checkride()
    assert report["measurements"] == {
        "scenario_count": 10,
        "accepted_count": 1,
        "hold_count": 9,
        "unsafe_ready_count": 0,
        "accepted_frame_count": 52,
        "accepted_baseline_frames": 12,
        "labels_accepted": 0,
        "capture_operations": 0,
        "tail_operations": 0,
        "checkpoint_writes": 0,
        "field_validations": 0,
        "candidate_acceptances": 0,
        "candidate_installations": 0,
        "deployments": 0,
        "hardware_actions": 0,
        "runtime_writes": 0,
    }
    preserved = json.loads(
        (ROOT / "docs/evidence/aegis-temperature-long-window-intake-v1.json").read_text()
    )
    assert preserved == report


def test_mobile_view_exposes_separate_long_window_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Governed Long-Window Intake" in source
    assert "One-shot snapshot · no tailing · labels forbidden" in source
    assert "The four-frame recovery intake is not reused" in source
    assert "@media(max-width:760px)" in source
