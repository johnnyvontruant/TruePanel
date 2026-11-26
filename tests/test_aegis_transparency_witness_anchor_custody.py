import copy
import json
from pathlib import Path

from truepanel.aegis.transparency_monitor_quorum import MONITOR_IDS
from truepanel.aegis.transparency_witness_anchor_custody import (
    CUSTODIAN_IDS,
    STATUS_HOLD,
    STATUS_REHEARSED,
    build_anchor_custody_statement,
    evaluate_threshold_anchor_custody,
)
from truepanel.aegis.transparency_witness_sqlite_recovery import (
    SQLiteWitnessDurableStateStore,
)
from truepanel.aegis.transparency_witness_storage_faults import create_recovery_anchor
from truepanel.holodeck.aegis_transparency_witness_anchor_custody import (
    run_transparency_witness_anchor_custody_checkride,
)
from truepanel.holodeck.aegis_transparency_witness_crash_recovery import _fixtures

ROOT = Path(__file__).resolve().parents[1]


def _fixture(tmp_path):
    continuity, transitions = _fixtures()
    stores = [
        SQLiteWitnessDurableStateStore(tmp_path / str(index), monitor_id)
        for index, monitor_id in enumerate(MONITOR_IDS)
    ]
    for store, transition in zip(stores, transitions, strict=True):
        store.initialize(transition["state_before"])
        store.commit(continuity, transition)
    anchor = create_recovery_anchor(stores)
    statement = build_anchor_custody_statement(anchor)
    signatures = [
        {"custodian_id": custodian_id, "signature": f"signature-{index}"}
        for index, custodian_id in enumerate(CUSTODIAN_IDS)
    ]
    fingerprints = {
        CUSTODIAN_IDS[0]: "SHA256:alpha",
        CUSTODIAN_IDS[1]: "SHA256:bravo",
    }
    return stores, anchor, statement, signatures, fingerprints


def test_exact_distinct_threshold_is_required(tmp_path):
    stores, anchor, statement, signatures, fingerprints = _fixture(tmp_path)
    accepted = evaluate_threshold_anchor_custody(
        stores, anchor, statement, signatures, lambda *_: True, fingerprints
    )
    assert accepted["status"] == STATUS_REHEARSED
    assert accepted["valid_custodian_count"] == 2
    assert accepted["eligible_for_production_trust"] is False
    assert accepted["physical_power_loss_validated"] is False

    missing = evaluate_threshold_anchor_custody(
        stores, anchor, statement, signatures[:1], lambda *_: True, fingerprints
    )
    assert missing["status"] == STATUS_HOLD
    assert "WitnessAnchorCustodyThresholdNotMet" in missing["errors"]


def test_duplicate_substitution_and_policy_downgrade_fail_closed(tmp_path):
    stores, anchor, statement, signatures, fingerprints = _fixture(tmp_path)
    duplicate = copy.deepcopy(signatures)
    duplicate[1]["custodian_id"] = duplicate[0]["custodian_id"]
    assert (
        evaluate_threshold_anchor_custody(
            stores, anchor, statement, duplicate, lambda *_: True, fingerprints
        )["status"]
        == STATUS_HOLD
    )

    changed = copy.deepcopy(statement)
    changed["subject"][0]["digest"]["sha256"] = "f" * 64
    assert (
        evaluate_threshold_anchor_custody(
            stores, anchor, changed, signatures, lambda *_: True, fingerprints
        )["status"]
        == STATUS_HOLD
    )

    downgraded = evaluate_threshold_anchor_custody(
        stores,
        anchor,
        statement,
        signatures,
        lambda *_: True,
        fingerprints,
        threshold=1,
    )
    assert "WitnessAnchorCustodyPolicyInvalid" in downgraded["errors"]


def test_checkride_matches_reviewed_threshold_custody_evidence():
    actual = run_transparency_witness_anchor_custody_checkride()
    expected = json.loads(
        (
            ROOT
            / "docs/evidence/aegis-transparency-witness-anchor-custody-checkride-v1.json"
        ).read_text()
    )
    assert actual == expected
    assert actual["measurements"]["scenario_count"] == 12
    assert actual["measurements"]["pass_count"] == 2
    assert actual["measurements"]["hold_count"] == 10
    assert actual["measurements"]["coverage_trusted"] == 15
    assert actual["measurements"]["anchor_rollback_acceptances"] == 0


def test_ci_mobile_and_prior_art_contracts():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "transparency-witness-anchor-custody:" in workflow
    assert "needs: transparency-witness-storage-faults" in workflow
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Threshold Anchor Custody" in source
    assert "2 / 2 CUSTODIANS · 15 / 15 COVERED" in source
    report = (ROOT / "docs/AEGIS_TRANSPARENCY_WITNESS_ANCHOR_CUSTODY.md").read_text()
    assert "The Update Framework" in report
    assert "in-toto" in report
    assert "physical power cut" in report
