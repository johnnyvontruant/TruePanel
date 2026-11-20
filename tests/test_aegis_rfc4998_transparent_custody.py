import copy
import hashlib
import json
from pathlib import Path

from truepanel.aegis.rfc4998_timestamped_custody import (
    SCHEMA as TIMESTAMPED_SCHEMA,
)
from truepanel.aegis.rfc4998_timestamped_custody import STATUS_TIMESTAMPED
from truepanel.aegis.rfc4998_transparent_custody import (
    CHECKPOINT_SCHEMA,
    KEY_ID,
    SCHEMA,
    STATUS_HOLD,
    STATUS_RECEIPT_REQUIRED,
    STATUS_TRANSPARENT,
    build_transparency_entry,
    consistency_proof,
    evaluate_transparent_custody,
    inclusion_proof,
    merkle_root,
    verify_consistency,
    verify_inclusion,
)
from truepanel.holodeck.aegis_rfc4998_transparent_custody import (
    run_rfc4998_transparent_custody_checkride,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT
    / "docs"
    / "evidence"
    / "aegis-rfc4998-timestamped-custody-checkride-v1.json"
)


def _timestamped():
    return {
        "schema": TIMESTAMPED_SCHEMA,
        "status": STATUS_TIMESTAMPED,
        "record_id": "record-1",
        "custody_id": "custody-1",
        "record_sha256": "7" * 64,
        "independent_signing_time_rehearsed": True,
        "production_trusted": False,
        "runtime_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "network_authority": False,
        "storage_authority": False,
    }


def _receipt(timestamped, evidence):
    entry = build_transparency_entry(timestamped, evidence)
    leaves = [b"genesis", entry, b"monitor"]
    prior = leaves[:2]
    return {
        "schema": SCHEMA,
        "log_key_id": KEY_ID,
        "leaf_index": 1,
        "entry_sha256": hashlib.sha256(entry).hexdigest(),
        "checkpoint": {
            "schema": CHECKPOINT_SCHEMA,
            "origin": "fixture-log",
            "tree_size": 3,
            "root_hash_sha256": merkle_root(leaves).hex(),
            "hash_algorithm": "sha256",
        },
        "checkpoint_signature": "current",
        "previous_checkpoint": {
            "schema": CHECKPOINT_SCHEMA,
            "origin": "fixture-log",
            "tree_size": 2,
            "root_hash_sha256": merkle_root(prior).hex(),
            "hash_algorithm": "sha256",
        },
        "previous_checkpoint_signature": "previous",
        "inclusion_path": [value.hex() for value in inclusion_proof(1, leaves)],
        "consistency_path": [value.hex() for value in consistency_proof(2, leaves)],
    }


def test_rfc9162_proofs_round_trip_non_power_of_two_trees():
    leaves = [f"leaf-{index}".encode() for index in range(9)]
    for size in range(1, len(leaves) + 1):
        root = merkle_root(leaves[:size])
        for index in range(size):
            proof = inclusion_proof(index, leaves[:size])
            assert verify_inclusion(leaves[index], index, size, proof, root)
        for prior_size in range(1, size + 1):
            proof = consistency_proof(prior_size, leaves[:size])
            assert verify_consistency(
                prior_size,
                size,
                merkle_root(leaves[:prior_size]),
                root,
                proof,
            )


def test_exact_receipt_verifies_without_granting_authority():
    timestamped = _timestamped()
    evidence = EVIDENCE.read_bytes()
    calls = []

    def verifier(key_id, payload, signature):
        calls.append((key_id, payload, signature))
        return True

    result = evaluate_transparent_custody(
        timestamped, evidence, _receipt(timestamped, evidence), verifier
    )
    assert result["status"] == STATUS_TRANSPARENT
    assert len(calls) == 2
    assert result["eligible_for_production_trust"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False
    assert result["active_runtime_record_validation"] == "PENDING"


def test_missing_tampered_and_authority_paths_fail_closed():
    timestamped = _timestamped()
    evidence = EVIDENCE.read_bytes()
    receipt = _receipt(timestamped, evidence)
    missing = evaluate_transparent_custody(timestamped, evidence, None, lambda *_: True)
    assert missing["status"] == STATUS_RECEIPT_REQUIRED

    tampered = copy.deepcopy(receipt)
    tampered["consistency_path"][0] = "00" * 32
    assert (
        evaluate_transparent_custody(timestamped, evidence, tampered, lambda *_: True)[
            "status"
        ]
        == STATUS_HOLD
    )

    malformed = evaluate_transparent_custody(
        timestamped, "not-bytes", "not-a-receipt", lambda *_: True
    )
    assert malformed["status"] == STATUS_HOLD
    assert "TimestampEvidenceInvalid" in malformed["errors"]
    assert "TransparencyReceiptInvalid" in malformed["errors"]

    escalated = copy.deepcopy(timestamped)
    escalated["deployment_authority"] = True
    assert (
        evaluate_transparent_custody(escalated, evidence, receipt, lambda *_: True)[
            "status"
        ]
        == STATUS_HOLD
    )


def test_real_checkride_matches_reviewed_evidence():
    actual = run_rfc4998_transparent_custody_checkride()
    expected = json.loads(
        (
            ROOT
            / "docs"
            / "evidence"
            / "aegis-rfc4998-transparent-custody-checkride-v1.json"
        ).read_text()
    )
    assert actual == expected
    assert actual["measurements"]["signed_append_only_receipts_verified"] == 1
    assert actual["measurements"]["hold_or_action_required_count"] == 9
    assert actual["measurements"]["network_calls"] == 0


def test_ci_and_mobile_mission_control_contract():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "rfc4998-transparent-custody:" in workflow
    assert "needs: rfc4998-timestamped-custody" in workflow
    assert "aegis-rfc4998-transparent-custody-checkride" in workflow

    source = (ROOT / "truepanel" / "web" / "static" / "reliability-view.js").read_text()
    assert "RFC 4998 Transparency Witness" in source
    assert "APPEND-ONLY REHEARSED" in source
    assert "Active record:" in source
    assert 'active_record_transparency||"PENDING"' in source
