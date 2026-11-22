import copy
import json
from pathlib import Path

from truepanel.aegis.transparency_monitor_quorum import MONITOR_IDS, SCHEMA as QUORUM_SCHEMA, STATUS_REHEARSED as QUORUM_REHEARSED
from truepanel.aegis.transparency_witness_continuity import TRANSITION_SCHEMA, STATUS_HOLD, STATUS_REHEARSED, checkpoint_digest, evaluate_witness_continuity
from truepanel.aegis.rfc4998_transparent_custody import consistency_proof, merkle_root
from truepanel.holodeck.aegis_transparency_witness_continuity import run_transparency_witness_continuity_checkride

ROOT = Path(__file__).resolve().parents[1]
DENIED = ("production_trusted", "runtime_authority", "deployment_authority", "hardware_authority", "network_authority", "storage_authority")


def _fixture():
    leaves = [b"a", b"b", b"c", b"d", b"e"]
    prior = {"origin": "log", "tree_size": 3, "root_hash_sha256": merkle_root(leaves[:3]).hex()}
    current = {"origin": "log", "tree_size": 5, "root_hash_sha256": merkle_root(leaves).hex()}
    quorum = {"schema": QUORUM_SCHEMA, "status": QUORUM_REHEARSED, "independent_monitor_quorum_rehearsed": True}
    quorum.update({name: False for name in DENIED})
    proof = [item.hex() for item in consistency_proof(3, leaves)]
    transitions = []
    for monitor_id in MONITOR_IDS:
        transitions.append({"schema": TRANSITION_SCHEMA, "monitor_id": monitor_id,
            "state_before": {"monitor_id": monitor_id, "origin": "log", "tree_size": 3, "root_hash_sha256": prior["root_hash_sha256"], "checkpoint_sha256": checkpoint_digest(prior), "state_sequence": 1},
            "state_after": {"monitor_id": monitor_id, "origin": "log", "tree_size": 5, "root_hash_sha256": current["root_hash_sha256"], "checkpoint_sha256": checkpoint_digest(current), "state_sequence": 2},
            "consistency_path": proof, "persisted_before_cosignature": True, "signature": "ok"})
    return quorum, prior, current, transitions


def test_continuity_requires_two_exact_monotonic_signed_ratchets():
    quorum, prior, current, transitions = _fixture()
    accepted = evaluate_witness_continuity(quorum, prior, current, transitions, lambda *_: True)
    assert accepted["status"] == STATUS_REHEARSED and accepted["valid_monitor_count"] == 2
    assert accepted["atomic_persistence_rehearsed"] is True
    assert accepted["eligible_for_production_trust"] is False
    assert evaluate_witness_continuity(quorum, prior, current, transitions[:1], lambda *_: True)["status"] == STATUS_HOLD
    stale = copy.deepcopy(transitions); stale[1]["state_before"]["tree_size"] = 2
    assert "WitnessOldSizeStale" in evaluate_witness_continuity(quorum, prior, current, stale, lambda *_: True)["errors"]
    bypass = copy.deepcopy(transitions); bypass[1]["persisted_before_cosignature"] = False
    assert "WitnessPersistenceOrderingInvalid" in evaluate_witness_continuity(quorum, prior, current, bypass, lambda *_: True)["errors"]


def test_checkride_matches_reviewed_evidence():
    actual = run_transparency_witness_continuity_checkride()
    expected = json.loads((ROOT / "docs/evidence/aegis-transparency-witness-continuity-checkride-v1.json").read_text())
    assert actual == expected
    assert actual["measurements"]["two_monitor_ratchets_verified"] == 1
    assert actual["measurements"]["hold_count"] == 11
    assert actual["measurements"]["network_calls"] == 0


def test_ci_and_mobile_contract():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "transparency-witness-continuity:" in workflow
    assert "needs: transparency-monitor-quorum" in workflow
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Witness State Continuity" in source
    assert "2 / 2 RATCHETS" in source
    assert "PERSIST BEFORE COSIGN" in source
