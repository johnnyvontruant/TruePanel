"""Contracts for the read-only AEGIS field ceremony coordinator."""

import json
from pathlib import Path

from truepanel.holodeck.aegis_field_ceremony import run_field_ceremony_checkride

ROOT = Path(__file__).resolve().parents[1]


def test_field_ceremony_names_actions_and_holds_invalid_evidence():
    evidence = run_field_ceremony_checkride()

    assert evidence["status_counts"] == {
        "ACTION_REQUIRED_INDEPENDENT_VERIFIER_CONFIRMATION": 1,
        "ACTION_REQUIRED_PUBLIC_ROSTER": 1,
        "ACTION_REQUIRED_SIGNING_KIT_EXPORT": 1,
        "ACTION_REQUIRED_INDEPENDENT_KIT_AUDIT": 1,
        "ACTION_REQUIRED_OFFLINE_SIGNATURE": 1,
        "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW": 1,
        "HOLD": 7,
    }
    assert evidence["measurements"]["operator_action_gates"] == 5
    assert evidence["measurements"]["development_eligible"] == 1
    assert evidence["measurements"]["unsafe_ready"] == 0
    assert evidence["measurements"]["production_acceptances"] == 0
    assert evidence["measurements"]["deployments"] == 0
    assert evidence["measurements"]["hardware_actions"] == 0
    assert evidence["measurements"]["runtime_writes"] == 0
    assert evidence["recovery_coverage"] == {"total": 8, "trusted": 8, "gaps": 0}


def test_preserved_field_ceremony_evidence_replays_exactly():
    archived = json.loads(
        (ROOT / "docs/evidence/aegis-field-ceremony-v1.json").read_text()
    )

    assert run_field_ceremony_checkride() == archived


def test_mission_control_names_field_ceremony_actions_and_holds():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()

    assert "Field ceremony · verifier fingerprint" in source
    assert "Missing JT-owned material · ACTION REQUIRED" in source
    assert "supplied invalid evidence · HOLD" in source
