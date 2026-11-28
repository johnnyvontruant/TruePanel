import json
from pathlib import Path

from truepanel.aegis.transparency_witness_anchor_rotation import build_custodian_root
from truepanel.aegis.transparency_witness_custodian_recovery import (
    CURRENT_CUSTODIAN_IDS,
    EXPANDED_CUSTODIAN_IDS,
    RECOVERED_CUSTODIAN_IDS,
    REVOKED_CUSTODIAN_ID,
    STATUS_HOLD,
    STATUS_REHEARSED,
    build_compromise_recovery_statement,
    evaluate_custodian_compromise_recovery,
)
from truepanel.holodeck.aegis_transparency_witness_custodian_recovery import (
    run_transparency_witness_custodian_recovery_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def _fixture():
    anchor = {"fixture": "anchor"}
    evidence = "a" * 64
    fingerprints = {
        identity: f"SHA256:{index}"
        for index, identity in enumerate(
            dict.fromkeys((*EXPANDED_CUSTODIAN_IDS, *RECOVERED_CUSTODIAN_IDS))
        )
    }
    current = build_custodian_root(
        version=2,
        anchor_statement=anchor,
        custodian_fingerprints={
            identity: fingerprints[identity] for identity in CURRENT_CUSTODIAN_IDS
        },
        custodian_ids=CURRENT_CUSTODIAN_IDS,
        predecessor_root_sha256="b" * 64,
        custody_evidence_sha256=evidence,
    )
    expanded = build_custodian_root(
        version=3,
        anchor_statement=anchor,
        custodian_fingerprints={
            identity: fingerprints[identity] for identity in EXPANDED_CUSTODIAN_IDS
        },
        custodian_ids=EXPANDED_CUSTODIAN_IDS,
        predecessor_root_sha256=current["root_sha256"],
        custody_evidence_sha256=evidence,
    )
    recovered = build_custodian_root(
        version=4,
        anchor_statement=anchor,
        custodian_fingerprints={
            identity: fingerprints[identity] for identity in RECOVERED_CUSTODIAN_IDS
        },
        custodian_ids=RECOVERED_CUSTODIAN_IDS,
        predecessor_root_sha256=expanded["root_sha256"],
        custody_evidence_sha256=evidence,
    )
    statement = build_compromise_recovery_statement(
        current, expanded, recovered, predecessor_evidence_sha256=evidence
    )

    def signatures(ids):
        return [
            {"custodian_id": identity, "signature": f"signature-{index}"}
            for index, identity in enumerate(ids)
        ]

    return (
        current,
        expanded,
        recovered,
        statement,
        signatures(CURRENT_CUSTODIAN_IDS),
        signatures(EXPANDED_CUSTODIAN_IDS[:2]),
        signatures(
            tuple(
                identity
                for identity in EXPANDED_CUSTODIAN_IDS
                if identity != REVOKED_CUSTODIAN_ID
            )
        ),
        signatures(RECOVERED_CUSTODIAN_IDS[:2]),
    )


def _evaluate(*, change=None):
    values = list(_fixture())
    if change:
        change(values)
    return evaluate_custodian_compromise_recovery(
        values[0],
        values[1],
        values[2],
        "a" * 64,
        values[3],
        values[4],
        values[5],
        values[6],
        values[7],
        lambda *_: True,
        lambda *_: True,
        lambda *_: True,
    )


def test_quorum_expansion_enables_one_key_compromise_recovery():
    result = _evaluate()
    assert result["status"] == STATUS_REHEARSED
    assert result["current_failure_tolerance"] == 0
    assert result["expanded_failure_tolerance"] == 1
    assert result["recovered_failure_tolerance"] == 1
    assert result["revoked_key_used_after_revocation"] is False
    assert result["eligible_for_production_trust"] is False


def test_loss_before_expansion_and_revoked_signing_fail_closed():
    lost = _evaluate(change=lambda values: values.__setitem__(4, values[4][:1]))
    assert lost["status"] == STATUS_HOLD
    assert "WitnessCustodianRecoveryExpansionCurrentThresholdNotMet" in lost["errors"]

    def use_revoked(values):
        values[6] = [
            values[6][0],
            {"custodian_id": REVOKED_CUSTODIAN_ID, "signature": "compromised"},
        ]

    compromised = _evaluate(change=use_revoked)
    assert compromised["status"] == STATUS_HOLD
    assert (
        "WitnessCustodianRecoveryRecoveryCurrentRevokedIdentityUsed"
        in compromised["errors"]
    )


def test_checkride_matches_reviewed_recovery_evidence():
    actual = run_transparency_witness_custodian_recovery_checkride()
    expected = json.loads(
        (
            ROOT
            / "docs/evidence/aegis-transparency-witness-custodian-recovery-checkride-v1.json"
        ).read_text()
    )
    assert actual == expected
    assert actual["measurements"]["scenario_count"] == 18
    assert actual["measurements"]["pass_count"] == 3
    assert actual["measurements"]["hold_count"] == 15
    assert actual["measurements"]["coverage_trusted"] == 21
    assert actual["measurements"]["revoked_key_post_revocation_acceptances"] == 0


def test_ci_mobile_and_prior_art_contracts():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "transparency-witness-custodian-recovery:" in workflow
    assert "needs: transparency-witness-anchor-rotation" in workflow
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Custodian Compromise Recovery" in source
    assert "2 / 2 → 2 / 3 → 2 / 3 · 21 / 21 COVERED" in source
    report = (
        ROOT / "docs/AEGIS_TRANSPARENCY_WITNESS_CUSTODIAN_RECOVERY.md"
    ).read_text()
    assert "NIST SP 800-57" in report
    assert "Sigstore" in report
    assert "loss-before-expansion" in report.lower()
