"""Regression contract for rejecting unsafe packets before operator signing."""

import json
from pathlib import Path

from truepanel.holodeck.aegis_operator_handoff import (
    run_operator_handoff_preflight_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_preflight_denies_stale_unsafe_and_unrehearsed_packets():
    report = run_operator_handoff_preflight_checkride()
    assert report["status_counts"] == {
        "READY_FOR_OFFLINE_SIGNATURE": 1,
        "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW": 1,
        "HOLD": 19,
        "DENIED": 5,
    }
    assert report["measurements"]["false_eligible_paths"] == 0
    assert report["measurements"]["adversarial_holds"] == 19
    assert report["production_keys"] == 0
    assert report["production_mutation"] is False
    assert report["control_authority"] is False
    assert all(
        scenario["status"] == "HOLD"
        for scenario in report["scenarios"]
        if scenario["scenario"].startswith("preflight-")
    )


def test_preflight_evidence_replays_exactly():
    archived = json.loads(
        (ROOT / "docs/evidence/aegis-operator-key-preflight-v1.json").read_text()
    )
    assert run_operator_handoff_preflight_checkride() == archived
