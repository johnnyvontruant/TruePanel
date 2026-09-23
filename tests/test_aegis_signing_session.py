"""Contracts for the content-bound development signing session."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from truepanel.aegis.signing_session import build_clock_witness
from truepanel.holodeck.aegis_signing_session import run_signing_session_checkride

ROOT = Path(__file__).parents[1]


def test_signing_session_binds_checkout_clock_handoff_and_receipt():
    result = run_signing_session_checkride()

    assert result["status_counts"] == {
        "READY_FOR_OFFLINE_SIGNATURE": 1,
        "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW": 1,
        "HOLD": 9,
    }
    assert result["measurements"]["false_ready"] == 0
    assert result["recovery_coverage"] == {"total": 8, "trusted": 8, "gaps": 0}
    assert result["production_mutation"] is False
    assert result["control_authority"] is False


def test_preserved_signing_session_evidence_replays_exactly():
    expected = json.loads(
        (ROOT / "docs/evidence/aegis-development-signing-session-v1.json").read_text()
    )

    assert run_signing_session_checkride() == expected


@pytest.mark.parametrize("value", [math.nan, math.inf, True])
def test_clock_witness_rejects_non_finite_or_boolean_time(value):
    with pytest.raises(ValueError, match="ClockWitnessInvalid"):
        build_clock_witness(
            observed_at="2026-09-19T12:00:00Z",
            unix_seconds=value,
            confirmed_by="jt",
        )
