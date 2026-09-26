"""Replay contract for the AEGIS independent signing-kit audit."""

from __future__ import annotations

import json
from pathlib import Path

from truepanel.holodeck.aegis_independent_kit_audit import (
    run_independent_kit_audit_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_independent_kit_audit_checkride_fails_closed():
    result = run_independent_kit_audit_checkride()
    assert result["status_counts"] == {
        "READY_FOR_OPERATOR_SIGNATURE": 1,
        "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW": 1,
        "HOLD": 12,
    }
    assert result["measurements"]["unsafe_ready"] == 0
    assert result["measurements"]["truepanel_imports_in_standalone"] == 0
    assert result["production_mutation"] is False
    assert result["control_authority"] is False


def test_preserved_independent_kit_audit_evidence_replays_exactly():
    expected = json.loads(
        (ROOT / "docs/evidence/aegis-independent-kit-audit-v1.json").read_text()
    )
    assert run_independent_kit_audit_checkride() == expected
