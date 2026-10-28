from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.holodeck.aegis_temperature_calibration_candidate_dossier import (
    run_temperature_calibration_candidate_dossier_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_view_holds_before_authenticated_dossier():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_calibration_candidate_dossier"
    ]
    assert result["status"] == "HOLD"
    assert result["candidate_review_ready"] is False
    assert result["candidate_accepted"] is False
    assert result["candidate_installed"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def test_candidate_dossier_rehearsal_fails_closed():
    report = run_temperature_calibration_candidate_dossier_checkride()
    assert report["measurements"] == {
        "scenario_count": 8,
        "ready_count": 1,
        "hold_count": 7,
        "coverage_total": 8,
        "coverage_trusted": 8,
        "coverage_gaps": 0,
        "lead_samples": 27,
        "unsafe_ready_count": 0,
        "candidate_acceptances": 0,
        "candidate_installations": 0,
        "deployments": 0,
        "hardware_actions": 0,
        "automatic_promotions": 0,
    }


def test_preserved_candidate_dossier_evidence_matches_checkride():
    preserved = json.loads(
        (
            ROOT
            / "docs/evidence/aegis-temperature-calibration-candidate-dossier-v1.json"
        ).read_text()
    )
    assert preserved == run_temperature_calibration_candidate_dossier_checkride()


def test_mobile_view_names_manual_review_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Calibration Candidate Dossier" in source
    assert "Decision + score + detector + coverage + HoloDeck" in source
    assert "it never validates, accepts, installs, deploys, or promotes" in source
    assert "@media(max-width:760px)" in source
