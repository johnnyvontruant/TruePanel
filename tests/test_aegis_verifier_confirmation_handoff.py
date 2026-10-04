"""Contracts for the release-bound verifier confirmation handoff."""

import json
from pathlib import Path

from truepanel.holodeck.aegis_verifier_confirmation_handoff import (
    run_verifier_confirmation_handoff_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_confirmation_handoff_is_release_bound_and_fail_closed():
    evidence = run_verifier_confirmation_handoff_checkride()

    assert evidence["status_counts"] == {
        "VERIFIER_CONFIRMATION_HANDOFF_VERIFIED": 1,
        "ACTION_REQUIRED_PUBLIC_ROSTER": 1,
        "HOLD": 12,
        "DENIED": 2,
    }
    measurements = evidence["measurements"]
    assert measurements["release_bound_handoffs"] == 1
    assert measurements["field_ceremony_next_gates"] == 1
    assert measurements["coherent_foreign_kits_accepted"] == 0
    assert measurements["private_keys_accepted_by_truepanel"] == 0
    assert measurements["signer_invocations_by_truepanel"] == 0
    assert measurements["cryptographic_independence_claims"] == 0
    assert measurements["production_acceptances"] == 0
    assert measurements["deployments"] == 0
    assert measurements["hardware_actions"] == 0
    assert measurements["runtime_writes"] == 0
    assert evidence["recovery_coverage"] == {"total": 8, "trusted": 8, "gaps": 0}


def test_preserved_confirmation_handoff_evidence_replays_exactly():
    preserved = json.loads(
        (ROOT / "docs/evidence/aegis-verifier-confirmation-handoff-v1.json").read_text()
    )
    assert preserved == run_verifier_confirmation_handoff_checkride()


def test_mission_control_names_release_binding_and_receipt_custody():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Release-bound kit · coherent foreign kits HOLD" in source
    assert "Receipt handoff · exclusive public files + expiry re-audit" in source
