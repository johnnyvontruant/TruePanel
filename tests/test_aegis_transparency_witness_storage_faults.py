import copy
import json
from pathlib import Path

from truepanel.aegis.transparency_monitor_quorum import MONITOR_IDS
from truepanel.aegis.transparency_witness_sqlite_recovery import (
    SQLiteWitnessDurableStateStore,
)
from truepanel.aegis.transparency_witness_storage_faults import (
    STATUS_HOLD,
    STATUS_REHEARSED,
    create_recovery_anchor,
    evaluate_anchored_witness_recovery,
)
from truepanel.holodeck.aegis_transparency_witness_crash_recovery import _fixtures
from truepanel.holodeck.aegis_transparency_witness_storage_faults import (
    run_transparency_witness_storage_fault_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def _committed_pair(tmp_path):
    continuity, transitions = _fixtures()
    stores = [
        SQLiteWitnessDurableStateStore(tmp_path / str(index), monitor_id)
        for index, monitor_id in enumerate(MONITOR_IDS)
    ]
    for store, transition in zip(stores, transitions, strict=True):
        store.initialize(transition["state_before"])
        store.commit(continuity, transition)
    return stores, create_recovery_anchor(stores)


def test_exact_two_store_recovery_matches_content_addressed_anchor(tmp_path):
    stores, anchor = _committed_pair(tmp_path)
    result = evaluate_anchored_witness_recovery(stores, anchor)
    assert result["status"] == STATUS_REHEARSED
    assert result["exact_anchor_match"] is True
    assert result["production_trusted"] is False
    assert result["physical_power_loss_validated"] is False


def test_matching_stale_stores_cannot_satisfy_newer_anchor(tmp_path):
    continuity, transitions = _fixtures()
    stores = [
        SQLiteWitnessDurableStateStore(tmp_path / str(index), monitor_id)
        for index, monitor_id in enumerate(MONITOR_IDS)
    ]
    for store, transition in zip(stores, transitions, strict=True):
        store.initialize(transition["state_before"])
    stale_images = [store.path.read_bytes() for store in stores]
    for store, transition in zip(stores, transitions, strict=True):
        store.commit(continuity, transition)
    anchor = create_recovery_anchor(stores)
    for store, image in zip(stores, stale_images, strict=True):
        store.path.write_bytes(image)
    assert evaluate_anchored_witness_recovery(stores, anchor)["status"] == STATUS_HOLD


def test_anchor_tamper_and_authority_escalation_fail_closed(tmp_path):
    stores, anchor = _committed_pair(tmp_path)
    tampered = dict(anchor)
    tampered["checkpoint_sha256"] = "f" * 64
    result = evaluate_anchored_witness_recovery(stores, tampered)
    assert result["status"] == STATUS_HOLD
    assert "WitnessRecoveryAnchorDigestMismatch" in result["errors"]
    escalated = copy.deepcopy(anchor)
    escalated["deployment_authority"] = True
    assert evaluate_anchored_witness_recovery(stores, escalated)["status"] == STATUS_HOLD


def test_checkride_matches_reviewed_fault_corpus():
    actual = run_transparency_witness_storage_fault_checkride()
    expected = json.loads(
        (
            ROOT
            / "docs/evidence/aegis-transparency-witness-storage-faults-checkride-v1.json"
        ).read_text()
    )
    assert actual == expected
    assert actual["measurements"]["scenario_count"] == 13
    assert actual["measurements"]["pass_count"] == 2
    assert actual["measurements"]["hold_count"] == 11
    assert actual["measurements"]["coverage_trusted"] == 13
    assert actual["measurements"]["stale_dual_store_acceptances"] == 0
    assert actual["measurements"]["physical_power_loss_validated"] == 0


def test_ci_mobile_and_prior_art_contracts():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "transparency-witness-storage-faults:" in workflow
    assert "needs: transparency-witness-sqlite-recovery" in workflow
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Anchored Storage Fault Corpus" in source
    assert "9 IMAGE FAULTS · 13 / 13 COVERED" in source
    report = (ROOT / "docs/AEGIS_TRANSPARENCY_WITNESS_STORAGE_FAULTS.md").read_text()
    assert "SQLite test VFS" in report
    assert "FoundationDB" in report
    assert "physical power cut" in report
