"""Contracts for short-lived verifier confirmation receipts."""

import json
from pathlib import Path

from truepanel.aegis.verifier_confirmation import (
    load_verifier_confirmation_document,
)
from truepanel.holodeck.aegis_verifier_confirmation import (
    run_verifier_confirmation_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_verifier_confirmation_is_bounded_operator_attestation():
    evidence = run_verifier_confirmation_checkride()

    assert evidence["status_counts"] == {
        "OPERATOR_ATTESTED_INDEPENDENT_CHANNEL": 1,
        "DENIED": 3,
        "HOLD": 10,
    }
    assert evidence["measurements"]["operator_attestations_verified"] == 1
    assert evidence["measurements"]["legacy_magic_string_paths"] == 0
    assert evidence["measurements"]["cryptographic_independence_claims"] == 0
    assert evidence["measurements"]["private_keys_accepted_by_truepanel"] == 0
    assert evidence["measurements"]["signer_invocations_by_truepanel"] == 0
    assert evidence["measurements"]["production_acceptances"] == 0
    assert evidence["measurements"]["deployments"] == 0
    assert evidence["measurements"]["hardware_actions"] == 0
    assert evidence["measurements"]["runtime_writes"] == 0
    assert evidence["recovery_coverage"] == {"total": 8, "trusted": 8, "gaps": 0}


def test_preserved_verifier_confirmation_evidence_replays_exactly():
    preserved = json.loads(
        (ROOT / "docs/evidence/aegis-verifier-confirmation-receipt-v1.json").read_text()
    )

    assert preserved == run_verifier_confirmation_checkride()


def test_mission_control_names_attestation_limit_and_expiry():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()

    assert "Verifier confirmation · exact full digest + named out-of-band method" in source
    assert "Operator attestation · expires in 30 minutes · not cryptographic proof" in source


def test_confirmation_document_loader_rejects_relative_and_symlinked_inputs(tmp_path):
    document = tmp_path / "confirmation.json"
    document.write_text('{"public":true}\n')
    linked = tmp_path / "linked.json"
    linked.symlink_to(document)

    assert load_verifier_confirmation_document(document.resolve()) == {"public": True}
    for unsafe in (Path("confirmation.json"), linked):
        try:
            load_verifier_confirmation_document(unsafe)
        except ValueError as error:
            assert str(error) == "VerifierConfirmationUnsafePath"
        else:
            raise AssertionError("unsafe confirmation input was accepted")
