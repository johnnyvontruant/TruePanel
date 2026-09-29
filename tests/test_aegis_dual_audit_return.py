"""Contracts for audit-bound returned development signatures."""

import json
from pathlib import Path

from truepanel.holodeck.aegis_dual_audit_return import (
    run_dual_audit_return_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_dual_audit_return_checkride_fails_closed():
    evidence = run_dual_audit_return_checkride()

    assert evidence["status_counts"] == {
        "READY_FOR_DUAL_AUDIT": 1,
        "READY_FOR_OPERATOR_SIGNATURE": 1,
        "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW": 1,
        "HOLD": 8,
    }
    assert evidence["measurements"]["signature_only_eligibility"] == 0
    assert evidence["measurements"]["unsafe_ready"] == 0
    assert evidence["measurements"]["production_acceptances"] == 0
    assert evidence["measurements"]["deployments"] == 0
    assert evidence["measurements"]["hardware_actions"] == 0
    assert evidence["measurements"]["runtime_writes"] == 0
    assert evidence["recovery_coverage"] == {"total": 8, "trusted": 8, "gaps": 0}


def test_dual_audit_return_evidence_replays_exactly():
    expected = json.loads(
        (ROOT / "docs/evidence/aegis-dual-audit-return-binding-v1.json").read_text()
    )

    assert run_dual_audit_return_checkride() == expected
