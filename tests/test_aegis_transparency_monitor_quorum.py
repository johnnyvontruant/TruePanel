import copy
import json
from pathlib import Path

from truepanel.aegis.rfc4998_transparent_custody import SCHEMA as TRANSPARENT_SCHEMA
from truepanel.aegis.rfc4998_transparent_custody import STATUS_TRANSPARENT
from truepanel.aegis.transparency_monitor_quorum import MONITOR_IDS, OBSERVATION_SCHEMA, STATUS_HOLD, STATUS_REHEARSED, checkpoint_digest, evaluate_monitor_quorum
from truepanel.holodeck.aegis_transparency_monitor_quorum import run_transparency_monitor_quorum_checkride

ROOT = Path(__file__).resolve().parents[1]


def _custody():
    result = {"schema": TRANSPARENT_SCHEMA, "status": STATUS_TRANSPARENT, "checkpoint_signature_verified": True,
              "append_only_consistency_verified": True, "inclusion_proof_verified": True}
    result.update({name: False for name in ("production_trusted", "runtime_authority", "deployment_authority", "hardware_authority", "network_authority", "storage_authority")})
    return result


def _fixture():
    checkpoint = {"origin": "log", "tree_size": 3, "root_hash_sha256": "a" * 64}
    observations = [{"schema": OBSERVATION_SCHEMA, "monitor_id": monitor_id, "checkpoint_sha256": checkpoint_digest(checkpoint),
                     "origin": "log", "tree_size": 3, "root_hash_sha256": "a" * 64, "signature": "ok"} for monitor_id in MONITOR_IDS]
    return checkpoint, observations


def test_quorum_requires_two_distinct_exact_signed_views():
    checkpoint, observations = _fixture()
    accepted = evaluate_monitor_quorum(_custody(), checkpoint, observations, lambda *_: True)
    assert accepted["status"] == STATUS_REHEARSED and accepted["valid_monitor_count"] == 2
    assert accepted["eligible_for_production_trust"] is False and accepted["active_runtime_record_validation"] == "PENDING"
    assert evaluate_monitor_quorum(_custody(), checkpoint, observations[:1], lambda *_: True)["status"] == STATUS_HOLD
    duplicate = copy.deepcopy(observations); duplicate[1]["monitor_id"] = duplicate[0]["monitor_id"]
    assert "MonitorObservationDuplicateIdentity" in evaluate_monitor_quorum(_custody(), checkpoint, duplicate, lambda *_: True)["errors"]
    fork = copy.deepcopy(observations); fork[1]["root_hash_sha256"] = "b" * 64
    rejected = evaluate_monitor_quorum(_custody(), checkpoint, fork, lambda *_: True)
    assert rejected["split_view_detected"] is True and "MonitorSplitViewDetected" in rejected["errors"]


def test_checkride_matches_reviewed_evidence():
    actual = run_transparency_monitor_quorum_checkride()
    expected = json.loads((ROOT / "docs/evidence/aegis-transparency-monitor-quorum-checkride-v1.json").read_text())
    assert actual == expected
    assert actual["measurements"]["two_monitor_quorums_verified"] == 1
    assert actual["measurements"]["hold_count"] == 9 and actual["measurements"]["network_calls"] == 0


def test_ci_and_mobile_contract():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "transparency-monitor-quorum:" in workflow and "needs: rfc4998-transparent-custody" in workflow
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Transparency Monitor Quorum" in source and "2 / 2" in source and "SIMULATED OPERATORS" in source
