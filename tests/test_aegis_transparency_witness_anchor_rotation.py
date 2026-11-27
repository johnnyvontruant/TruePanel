import copy
import hashlib
import json
from pathlib import Path

from truepanel.aegis.transparency_witness_anchor_rotation import (
    CURRENT_CUSTODIAN_IDS,
    NEXT_CUSTODIAN_IDS,
    STATUS_HOLD,
    STATUS_REHEARSED,
    build_custodian_root,
    build_rotation_statement,
    evaluate_custodian_root_rotation,
)
from truepanel.holodeck.aegis_transparency_witness_anchor_rotation import (
    run_transparency_witness_anchor_rotation_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def _fixture():
    anchor_statement = {"fixture": "exact-anchor-statement"}
    current_fingerprints = {
        CURRENT_CUSTODIAN_IDS[0]: "SHA256:alpha",
        CURRENT_CUSTODIAN_IDS[1]: "SHA256:bravo",
    }
    next_fingerprints = {
        NEXT_CUSTODIAN_IDS[0]: "SHA256:bravo",
        NEXT_CUSTODIAN_IDS[1]: "SHA256:charlie",
    }
    current_root = build_custodian_root(
        version=1,
        anchor_statement=anchor_statement,
        custodian_fingerprints=current_fingerprints,
        custodian_ids=CURRENT_CUSTODIAN_IDS,
        predecessor_root_sha256=None,
        custody_evidence_sha256="a" * 64,
    )
    next_root = build_custodian_root(
        version=2,
        anchor_statement=anchor_statement,
        custodian_fingerprints=next_fingerprints,
        custodian_ids=NEXT_CUSTODIAN_IDS,
        predecessor_root_sha256=current_root["root_sha256"],
        custody_evidence_sha256="a" * 64,
    )
    statement = build_rotation_statement(current_root, next_root)
    current_signatures = [
        {"custodian_id": identity, "signature": f"current-{index}"}
        for index, identity in enumerate(CURRENT_CUSTODIAN_IDS)
    ]
    next_signatures = [
        {"custodian_id": identity, "signature": f"next-{index}"}
        for index, identity in enumerate(NEXT_CUSTODIAN_IDS)
    ]
    return (
        anchor_statement,
        current_root,
        next_root,
        statement,
        current_signatures,
        next_signatures,
    )


def _evaluate(*, change=None):
    values = list(_fixture())
    if change is not None:
        change(values)
    return evaluate_custodian_root_rotation(
        values[1],
        values[2],
        values[0],
        "a" * 64,
        values[3],
        values[4],
        values[5],
        lambda *_: True,
        lambda *_: True,
    )


def test_exact_rotation_requires_both_thresholds():
    result = _evaluate()
    assert result["status"] == STATUS_REHEARSED
    assert result["current_threshold_verified"] is True
    assert result["next_threshold_verified"] is True
    assert result["eligible_for_production_trust"] is False

    missing_current = _evaluate(
        change=lambda values: values.__setitem__(4, values[4][:1])
    )
    assert missing_current["status"] == STATUS_HOLD
    assert "WitnessAnchorRotationCurrentThresholdNotMet" in missing_current["errors"]

    missing_next = _evaluate(change=lambda values: values.__setitem__(5, values[5][:1]))
    assert missing_next["status"] == STATUS_HOLD
    assert "WitnessAnchorRotationNextThresholdNotMet" in missing_next["errors"]


def test_version_skip_threshold_downgrade_and_authority_fail_closed():
    def skip(values):
        values[2] = build_custodian_root(
            version=3,
            anchor_statement=values[0],
            custodian_fingerprints=values[2]["custodian_fingerprints"],
            custodian_ids=NEXT_CUSTODIAN_IDS,
            predecessor_root_sha256=values[1]["root_sha256"],
            custody_evidence_sha256="a" * 64,
        )
        values[3] = build_rotation_statement(values[1], values[2])

    skipped = _evaluate(change=skip)
    assert skipped["status"] == STATUS_HOLD
    assert "WitnessAnchorRotationVersionNotConsecutive" in skipped["errors"]

    def downgrade(values):
        changed = copy.deepcopy(values[2])
        changed["threshold"] = 1
        payload = {key: value for key, value in changed.items() if key != "root_sha256"}
        changed["root_sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        values[2] = changed
        values[3] = build_rotation_statement(values[1], changed)

    downgraded = _evaluate(change=downgrade)
    assert downgraded["status"] == STATUS_HOLD
    assert "WitnessAnchorRotationNextRootInvalid" in downgraded["errors"]

    def escalate(values):
        values[3] = copy.deepcopy(values[3])
        values[3]["predicate"]["deployment_authority"] = True

    authority = _evaluate(change=escalate)
    assert authority["status"] == STATUS_HOLD
    assert "WitnessAnchorRotationAuthorityEscalation" in authority["errors"]


def test_checkride_matches_reviewed_rotation_evidence():
    actual = run_transparency_witness_anchor_rotation_checkride()
    expected = json.loads(
        (
            ROOT
            / "docs/evidence/aegis-transparency-witness-anchor-rotation-checkride-v1.json"
        ).read_text()
    )
    assert actual == expected
    assert actual["measurements"]["scenario_count"] == 16
    assert actual["measurements"]["pass_count"] == 2
    assert actual["measurements"]["hold_count"] == 14
    assert actual["measurements"]["coverage_trusted"] == 18
    assert actual["measurements"]["rollback_or_version_skip_acceptances"] == 0


def test_ci_mobile_and_prior_art_contracts():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "transparency-witness-anchor-rotation:" in workflow
    assert "needs: transparency-witness-anchor-custody" in workflow
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Custodian Root Rotation" in source
    assert "OLD 2 / 2 + NEW 2 / 2 · 18 / 18 COVERED" in source
    report = (ROOT / "docs/AEGIS_TRANSPARENCY_WITNESS_ANCHOR_ROTATION.md").read_text()
    assert "The Update Framework" in report
    assert "Sigstore" in report
    assert "physical power-cut" in report
