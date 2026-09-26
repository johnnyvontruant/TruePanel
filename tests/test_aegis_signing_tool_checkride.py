"""Replay contract for the public-only signing-tool checkride."""

from __future__ import annotations

import json
from pathlib import Path

from truepanel.holodeck.aegis_signing_tool import run_signing_tool_checkride

ROOT = Path(__file__).resolve().parents[1]


def test_signing_tool_checkride_fails_closed():
    result = run_signing_tool_checkride()
    assert result["status_counts"] == {
        "READY_FOR_DUAL_AUDIT": 1,
        "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW": 1,
        "HOLD": 8,
    }
    assert result["measurements"]["unsafe_ready"] == 0
    assert result["measurements"]["private_keys_accepted_by_truepanel"] == 0
    assert result["measurements"]["signer_invocations_by_truepanel"] == 0
    assert result["production_mutation"] is False
    assert result["control_authority"] is False


def test_preserved_signing_tool_evidence_replays_exactly():
    expected = json.loads(
        (ROOT / "docs/evidence/aegis-offline-signing-tool-v1.json").read_text()
    )
    assert run_signing_tool_checkride() == expected
