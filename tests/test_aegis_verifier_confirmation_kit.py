"""Contracts for the public-only verifier comparison kit."""

import json
from pathlib import Path

from truepanel.holodeck.aegis_verifier_confirmation_kit import (
    run_verifier_confirmation_kit_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_confirmation_kit_is_public_auditable_and_fail_closed():
    evidence = run_verifier_confirmation_kit_checkride()

    assert evidence["status_counts"] == {
        "READY_FOR_OPERATOR_COMPARISON": 1,
        "OPERATOR_ATTESTED_INDEPENDENT_CHANNEL": 1,
        "HOLD": 10,
        "DENIED": 2,
    }
    assert evidence["measurements"]["public_kits_ready"] == 1
    assert evidence["measurements"]["operator_attestations_verified"] == 1
    assert evidence["measurements"]["private_keys_accepted_by_truepanel"] == 0
    assert evidence["measurements"]["signer_invocations_by_truepanel"] == 0
    assert evidence["measurements"]["cryptographic_independence_claims"] == 0
    assert evidence["measurements"]["production_acceptances"] == 0
    assert evidence["measurements"]["deployments"] == 0
    assert evidence["measurements"]["hardware_actions"] == 0
    assert evidence["measurements"]["runtime_writes"] == 0
    assert evidence["recovery_coverage"] == {"total": 8, "trusted": 8, "gaps": 0}


def test_preserved_confirmation_kit_evidence_replays_exactly():
    preserved = json.loads(
        (ROOT / "docs/evidence/aegis-verifier-confirmation-kit-v1.json").read_text()
    )
    assert preserved == run_verifier_confirmation_kit_checkride()


def test_mission_control_names_public_kit_and_custody_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Comparison kit · public challenge + derived card + manifest" in source
    assert "Audit before attesting · kit is not the independent source" in source
