import copy
import json
import multiprocessing
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from truepanel.aegis.transparency_monitor_quorum import MONITOR_IDS
from truepanel.aegis.transparency_witness_crash_recovery import WitnessStateError
from truepanel.aegis.transparency_witness_sqlite_recovery import (
    STATUS_HOLD,
    STATUS_REHEARSED,
    SQLiteWitnessDurableStateStore,
    evaluate_isolated_witness_stores,
)
from truepanel.holodeck.aegis_transparency_witness_crash_recovery import _fixtures
from truepanel.holodeck.aegis_transparency_witness_sqlite_recovery import (
    _crash_worker,
    run_transparency_witness_sqlite_recovery_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def _pair(tmp_path: Path):
    continuity, transitions = _fixtures()
    stores = [
        SQLiteWitnessDurableStateStore(tmp_path / str(index), monitor_id)
        for index, monitor_id in enumerate(MONITOR_IDS)
    ]
    for store, transition in zip(stores, transitions, strict=True):
        store.initialize(transition["state_before"])
    return stores, continuity, transitions


def test_two_isolated_sqlite_stores_agree_without_production_authority(tmp_path):
    stores, continuity, transitions = _pair(tmp_path)
    for store, transition in zip(stores, transitions, strict=True):
        committed = store.commit(continuity, transition)
        assert committed["signature_released_after_sqlite_commit"] is True
        assert committed["storage_authority"] is False
    result = evaluate_isolated_witness_stores(stores)
    assert result["status"] == STATUS_REHEARSED
    assert result["checkpoint_agreement"] is True
    assert result["independent_production_monitor_operators"] == 0
    assert result["physical_power_loss_validated"] is False
    for store in stores:
        assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
        settings = store.recover()["sqlite_settings"]
        assert settings == {
            "journal_mode": "WAL",
            "synchronous": 2,
            "busy_timeout_ms": 1000,
        }


@pytest.mark.parametrize(
    ("stage", "expected_sequence", "signature_recoverable"),
    [
        ("before_begin", 7, False),
        ("after_begin", 7, False),
        ("after_write_before_commit", 7, False),
        ("after_commit_before_response", 8, True),
    ],
)
def test_sigkill_recovery_is_atomic(
    tmp_path, stage, expected_sequence, signature_recoverable
):
    stores, continuity, transitions = _pair(tmp_path)
    context = multiprocessing.get_context("fork")
    process = context.Process(
        target=_crash_worker,
        args=(
            str(stores[0].root),
            stores[0].monitor_id,
            continuity,
            transitions[0],
            stage,
        ),
    )
    process.start()
    process.join(timeout=10)
    assert process.exitcode == -9
    recovered = stores[0].recover()
    assert recovered["record"]["state"]["state_sequence"] == expected_sequence
    assert (recovered["recoverable_signature"] is not None) is signature_recoverable


def test_transactional_compare_and_swap_rejects_concurrent_fork(tmp_path):
    stores, continuity, transitions = _pair(tmp_path)
    fork = copy.deepcopy(transitions[0])
    fork["signature"] = "fork-signature"
    barrier = Barrier(2)

    def compete(transition):
        barrier.wait()
        try:
            return stores[0].commit(continuity, transition)["status"]
        except WitnessStateError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(
            future.result()
            for future in (
                executor.submit(compete, transitions[0]),
                executor.submit(compete, fork),
            )
        )
    assert outcomes == [
        "WITNESS_STATE_DURABLY_COMMITTED",
        "WitnessCommittedStateConflict",
    ]


def test_corrupt_or_nonisolated_store_holds_quorum(tmp_path):
    stores, continuity, transitions = _pair(tmp_path)
    for store, transition in zip(stores, transitions, strict=True):
        store.commit(continuity, transition)
    stores[1].path.write_bytes(b"corrupt")
    assert evaluate_isolated_witness_stores(stores)["status"] == STATUS_HOLD
    duplicate = SQLiteWitnessDurableStateStore(
        stores[0].root, stores[0].monitor_id
    )
    result = evaluate_isolated_witness_stores([stores[0], duplicate])
    assert result["status"] == STATUS_HOLD
    assert "WitnessStoreIdentityDuplicate" in result["errors"]
    assert "WitnessStorePathNotIsolated" in result["errors"]


def test_process_halt_is_unreachable_without_explicit_test_mode(tmp_path):
    stores, continuity, transitions = _pair(tmp_path)
    with pytest.raises(WitnessStateError, match="WitnessTestProcessHaltNotAllowed"):
        stores[0].commit(continuity, transitions[0], test_halt_at="after_begin")
    assert os.getpid() > 1


def test_checkride_matches_reviewed_evidence():
    actual = run_transparency_witness_sqlite_recovery_checkride()
    expected = json.loads(
        (
            ROOT
            / "docs/evidence/aegis-transparency-witness-sqlite-recovery-checkride-v1.json"
        ).read_text()
    )
    assert actual == expected
    assert actual["measurements"]["scenario_count"] == 14
    assert actual["measurements"]["abrupt_process_crash_points_rehearsed"] == 4
    assert actual["measurements"]["coverage_trusted"] == 12
    assert actual["measurements"]["physical_power_loss_validated"] == 0


def test_ci_and_mobile_contract():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "transparency-witness-sqlite-recovery:" in workflow
    assert "needs: transparency-witness-crash-recovery" in workflow
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Isolated Witness Stores" in source
    assert "2 STORES · WAL + FULL" in source
    assert "PROCESS SIGKILL ≠ POWER LOSS" in source
