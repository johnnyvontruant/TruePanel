"""Replay contract for the AEGIS signing-kit custody audit."""

from __future__ import annotations

import json
from pathlib import Path

from truepanel.holodeck.aegis_signing_kit_audit import run_signing_kit_audit_checkride

ROOT = Path(__file__).resolve().parents[1]


def test_signing_kit_audit_checkride_fails_closed():
    result = run_signing_kit_audit_checkride()
    assert result["status_counts"] == {
        "INTERNAL_AUDIT_PASS": 1,
        "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW": 1,
        "HOLD": 10,
    }
    assert result["measurements"]["unsafe_ready"] == 0
    assert result["measurements"]["review_card_substitutions_accepted"] == 0
    assert result["measurements"]["private_keys_accepted_by_truepanel"] == 0
    assert result["production_mutation"] is False
    assert result["control_authority"] is False


def test_preserved_signing_kit_audit_evidence_replays_exactly():
    expected = json.loads(
        (ROOT / "docs/evidence/aegis-signing-kit-custody-audit-v1.json").read_text()
    )
    assert run_signing_kit_audit_checkride() == expected
