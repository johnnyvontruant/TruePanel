import copy
import json
from pathlib import Path

import pytest

from truepanel.aegis.transparency_monitor_quorum import MONITOR_IDS
from truepanel.aegis.transparency_witness_crash_recovery import (
    STATUS_COMMITTED,
    STATUS_REPLAYED,
    InjectedCrash,
    WitnessDurableStateStore,
    WitnessStateError,
)
from truepanel.holodeck.aegis_transparency_witness_crash_recovery import (
    _fixtures,
    run_transparency_witness_crash_recovery_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def _store(tmp_path: Path):
    continuity, transitions = _fixtures()
    transition = transitions[0]
    store = WitnessDurableStateStore(tmp_path / "state", MONITOR_IDS[0])
    store.initialize(transition["state_before"])
    return store, continuity, transition


def test_commit_is_durable_before_signature_release_and_replay_safe(tmp_path):
    store, continuity, transition = _store(tmp_path)
    committed = store.commit(continuity, transition)
    assert committed["status"] == STATUS_COMMITTED
    assert committed["signature_released_after_durable_commit"] is True
    assert committed["storage_authority"] is False
    recovered = store.recover()
    assert recovered["record"]["state"]["state_sequence"] == 8
    assert recovered["recoverable_signature"] == transition["signature"]
    assert store.commit(continuity, transition)["status"] == STATUS_REPLAYED


@pytest.mark.parametrize(
    ("stage", "expected_sequence", "signature_recoverable"),
    [
        ("before_temp_write", 7, False),
        ("after_temp_fsync", 7, False),
        ("after_replace", 8, True),
        ("after_directory_fsync", 8, True),
    ],
)
def test_injected_crashes_recover_without_rollback_or_signature_leak(
    tmp_path, stage, expected_sequence, signature_recoverable
):
    store, continuity, transition = _store(tmp_path)
    with pytest.raises(InjectedCrash, match=stage):
        store.commit(continuity, transition, crash_at=stage)
    recovered = store.recover()
    assert recovered["record"]["state"]["state_sequence"] == expected_sequence
    assert (recovered["recoverable_signature"] is not None) is signature_recoverable
    result = store.commit(continuity, transition)
    assert result["status"] == (
        STATUS_REPLAYED if signature_recoverable else STATUS_COMMITTED
    )


def test_serialized_compare_and_swap_rejects_stale_or_forked_update(tmp_path):
    store, continuity, transition = _store(tmp_path)
    assert store.commit(continuity, transition)["status"] == STATUS_COMMITTED
    fork = copy.deepcopy(transition)
    fork["signature"] = "different-signature"
    with pytest.raises(WitnessStateError, match="WitnessCommittedStateConflict"):
        store.commit(continuity, fork)


def test_corruption_and_authority_escalation_fail_closed(tmp_path):
    store, continuity, transition = _store(tmp_path)
    record = store.read()
    record["state"]["state_sequence"] = 99
    store.path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(WitnessStateError, match="WitnessStateDigestMismatch"):
        store.read()

    store, continuity, transition = _store(tmp_path / "other")
    escalated = dict(continuity)
    escalated["deployment_authority"] = True
    with pytest.raises(WitnessStateError, match="WitnessContinuityAuthorityEscalation"):
        store.commit(escalated, transition)


def test_checkride_matches_reviewed_evidence():
    actual = run_transparency_witness_crash_recovery_checkride()
    expected = json.loads(
        (
            ROOT
            / "docs/evidence/aegis-transparency-witness-crash-recovery-checkride-v1.json"
        ).read_text()
    )
    assert actual == expected
    assert actual["measurements"]["scenario_count"] == 14
    assert actual["measurements"]["crash_points_rehearsed"] == 4
    assert actual["measurements"]["rollback_acceptances"] == 0
    assert actual["measurements"]["coverage_trusted"] == 11


def test_ci_and_mobile_contract():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "transparency-witness-crash-recovery:" in workflow
    assert "needs: transparency-witness-continuity" in workflow
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Witness Crash Recovery" in source
    assert "4 / 4 CRASH POINTS" in source
    assert "FSYNC → REPLACE → DIR FSYNC" in source
