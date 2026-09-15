import json
import os
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from truepanel.aegis import (
    ACCEPTANCE_SCHEMA,
    TRUST_POLICY_SCHEMA,
    OpenSshSignatureVerifier,
    assemble_acceptance_receipt,
    build_review_bundle,
    semantic_sha256,
    validate_allowed_signers_roster,
    validate_review_bundle,
)
from truepanel.holodeck.aegis_two_person_ceremony import (
    run_two_person_ceremony_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def _materials():
    candidate = {"candidate_id": "candidate-v2"}
    appraisal = {"status": "READY_FOR_OPERATOR_REVIEW"}
    predecessor = {"envelope_id": "accepted-v1"}
    request = {"request_id": "stage-request-v2", "stage_tree_sha256": "a" * 64}
    policy = {
        "schema": TRUST_POLICY_SCHEMA,
        "threshold": 2,
        "keys": [
            {"key_id": "reviewer-a", "reviewer_id": "release-a"},
            {"key_id": "reviewer-b", "reviewer_id": "safety-b"},
        ],
    }
    receipt = {
        "schema": ACCEPTANCE_SCHEMA,
        "receipt_id": "receipt-v2",
        "decision": "ACCEPTED_FOR_OPERATOR_PROMOTION",
        "candidate_envelope_sha256": semantic_sha256(candidate),
        "appraisal_sha256": semantic_sha256(appraisal),
        "predecessor_envelope_sha256": semantic_sha256(predecessor),
        "promotion_request_sha256": semantic_sha256(request),
        "issued_at": "2026-09-10T04:00:00Z",
        "expires_at": "2026-09-11T04:00:00Z",
        "environment": "HOLODECK",
    }
    bundle = build_review_bundle(
        receipt=receipt,
        candidate=candidate,
        appraisal=appraisal,
        predecessor=predecessor,
        promotion_request=request,
        trust_policy=policy,
    )
    return bundle


def test_review_bundle_binds_statement_subjects_and_policy():
    bundle = _materials()
    assert (
        validate_review_bundle(bundle)["status"] == "READY_FOR_INDEPENDENT_SIGNATURES"
    )

    changed = deepcopy(bundle)
    changed["subjects"]["promotion_request"]["stage_tree_sha256"] = "b" * 64
    assert validate_review_bundle(changed)["status"] == "HOLD"

    changed = deepcopy(bundle)
    changed["trust_policy"]["threshold"] = 1
    assert validate_review_bundle(changed)["status"] == "HOLD"

    changed = deepcopy(bundle)
    changed["operator_note"] = "this field is not signed"
    assert validate_review_bundle(changed)["reason"] == "ReviewBundleFieldsInvalid"


def test_receipt_assembly_never_signs_or_accepts():
    bundle = _materials()
    receipt = assemble_acceptance_receipt(
        bundle,
        [{"key_id": "reviewer-a", "reviewer_id": "release-a", "signature": "detached"}],
    )
    assert receipt["signatures"][0]["signature"] == "detached"
    assert "subjects" not in receipt
    assert bundle["signing_authority"] is False
    assert bundle["promotion_authority"] is False

    changed = deepcopy(bundle)
    changed["statement_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="ReviewStatementDigestInvalid"):
        assemble_acceptance_receipt(changed, [])


def _public_key(tmp_path: Path) -> str:
    key = tmp_path / "roster-key"
    subprocess.run(
        ["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
        check=True,
    )
    return key.with_suffix(".pub").read_text(encoding="ascii").strip()


def test_strict_roster_rejects_flexible_openssh_features(tmp_path):
    public = _public_key(tmp_path)
    exact = f"reviewer-a {public}\n".encode()
    roster = validate_allowed_signers_roster(exact, expected_key_ids=("reviewer-a",))
    assert set(roster) == {"reviewer-a"}
    assert roster["reviewer-a"].startswith("SHA256:")

    for unsafe in (
        f"* {public}\n",
        f"reviewer-a,reviewer-b {public}\n",
        f"cert-authority reviewer-a {public}\n",
        f"reviewer-a {public}\nreviewer-extra {public}\n",
        "reviewer-a ssh-ed25519 c3NoLWVkMjU1MTk=\n",
    ):
        with pytest.raises(ValueError):
            validate_allowed_signers_roster(
                unsafe.encode(), expected_key_ids=("reviewer-a",)
            )


def test_verifier_rejects_roster_policy_mismatch(tmp_path):
    public = _public_key(tmp_path)
    allowed = tmp_path / "allowed_signers"
    allowed.write_text(f"reviewer-a {public}\n", encoding="ascii")
    os.chmod(allowed, 0o600)
    verifier = OpenSshSignatureVerifier(
        allowed, expected_key_ids=("reviewer-a", "reviewer-b")
    )
    assert verifier("reviewer-a", b"statement", "not-a-signature") is False


def test_two_person_ceremony_checkride_stops_before_promotion():
    report = run_two_person_ceremony_checkride()
    assert report["status_counts"] == {"READY_FOR_MANUAL_PROMOTION": 1, "HOLD": 8}
    assert report["measurements"]["false_ready_paths"] == 0
    assert report["measurements"]["private_keys_in_bundle"] == 0
    assert report["measurements"]["promotion_executions"] == 0
    assert report["production_mutation"] is False
    assert report["control_authority"] is False


def test_preserved_two_person_ceremony_evidence_replays_exactly():
    archived = json.loads(
        (ROOT / "docs/evidence/aegis-two-person-ceremony-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert run_two_person_ceremony_checkride() == archived
