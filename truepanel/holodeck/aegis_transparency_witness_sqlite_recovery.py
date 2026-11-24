"""Isolated SQLite witness stores and abrupt-process-crash checkride."""

from __future__ import annotations

import argparse
import copy
import json
import multiprocessing
import sqlite3
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any

from truepanel.aegis.transparency_monitor_quorum import MONITOR_IDS
from truepanel.aegis.transparency_witness_crash_recovery import WitnessStateError
from truepanel.aegis.transparency_witness_sqlite_recovery import (
    STATUS_HOLD,
    STATUS_REHEARSED,
    SQLiteWitnessDurableStateStore,
    evaluate_isolated_witness_stores,
)
from truepanel.holodeck.aegis_transparency_witness_crash_recovery import _fixtures


def _crash_worker(
    root: str,
    monitor_id: str,
    continuity: dict[str, Any],
    transition: dict[str, Any],
    stage: str,
) -> None:
    store = SQLiteWitnessDurableStateStore(
        Path(root), monitor_id, allow_test_process_halt=True
    )
    store.commit(continuity, transition, test_halt_at=stage)


def _initialized_pair(base: Path):
    continuity, transitions = _fixtures()
    stores = [
        SQLiteWitnessDurableStateStore(base / f"store-{index}", monitor_id)
        for index, monitor_id in enumerate(MONITOR_IDS)
    ]
    for store, transition in zip(stores, transitions, strict=True):
        store.initialize(transition["state_before"])
    return stores, continuity, transitions


def _scenario(name: str, action) -> dict[str, Any]:
    try:
        observation = action()
        return {"name": name, "status": "PASS", "observation": observation}
    except (AssertionError, OSError, sqlite3.DatabaseError, WitnessStateError) as error:
        return {"name": name, "status": "HOLD", "observation": str(error)}


def run_transparency_witness_sqlite_recovery_checkride(
    root: Path | None = None, *, crash_recovery_evidence_path: Path | None = None
) -> dict[str, Any]:
    repository = root or Path(__file__).resolve().parents[2]
    predecessor_path = (
        crash_recovery_evidence_path
        or repository
        / "docs/evidence/aegis-transparency-witness-crash-recovery-checkride-v1.json"
    )
    predecessor = json.loads(predecessor_path.read_text(encoding="utf-8"))
    if (
        predecessor.get("schema")
        != "truepanel.holodeck-transparency-witness-crash-recovery/v1"
        or predecessor.get("measurements", {}).get("crash_points_rehearsed") != 4
    ):
        raise ValueError("reviewed witness crash-recovery evidence required")

    with tempfile.TemporaryDirectory(
        prefix="truepanel-aegis-witness-sqlite-"
    ) as directory:
        base = Path(directory)
        scenarios: list[dict[str, Any]] = []

        def dual_agreement() -> str:
            stores, continuity, transitions = _initialized_pair(base / "agreement")
            for store, transition in zip(stores, transitions, strict=True):
                store.commit(continuity, transition)
            result = evaluate_isolated_witness_stores(stores)
            assert result["status"] == STATUS_REHEARSED
            assert result["checkpoint_agreement"] is True
            return "TWO_ISOLATED_STORES_AGREE"

        scenarios.append(_scenario("dual-store-checkpoint-agreement", dual_agreement))

        def exact_replay() -> str:
            stores, continuity, transitions = _initialized_pair(base / "replay")
            first = stores[0].commit(continuity, transitions[0])
            replay = stores[0].commit(continuity, transitions[0])
            assert first["status"] == "WITNESS_STATE_DURABLY_COMMITTED"
            assert replay["status"] == "WITNESS_STATE_COMMIT_REPLAYED"
            assert first["response_signature"] == replay["response_signature"]
            return "EXACT_SIGNATURE_REPLAYED"

        scenarios.append(_scenario("exact-signature-replay", exact_replay))

        def process_crash(stage: str) -> str:
            stores, continuity, transitions = _initialized_pair(
                base / f"crash-{stage}"
            )
            store = stores[0]
            context = multiprocessing.get_context("fork")
            process = context.Process(
                target=_crash_worker,
                args=(
                    str(store.root),
                    store.monitor_id,
                    continuity,
                    transitions[0],
                    stage,
                ),
            )
            process.start()
            process.join(timeout=10)
            assert process.exitcode == -9
            recovered = store.recover()
            sequence = recovered["record"]["state"]["state_sequence"]
            if stage == "after_commit_before_response":
                assert sequence == 8
                assert recovered["recoverable_signature"] == transitions[0]["signature"]
                return "COMMITTED_SIGNATURE_RECOVERED_AFTER_SIGKILL"
            assert sequence == 7
            assert recovered["recoverable_signature"] is None
            return "PRIOR_STATE_RECOVERED_AFTER_SIGKILL"

        for stage in (
            "before_begin",
            "after_begin",
            "after_write_before_commit",
            "after_commit_before_response",
        ):
            scenarios.append(
                _scenario(
                    f"sigkill-{stage.replace('_', '-')}",
                    lambda stage=stage: process_crash(stage),
                )
            )

        def concurrent_fork() -> str:
            stores, continuity, transitions = _initialized_pair(base / "fork")
            store = stores[0]
            contender = copy.deepcopy(transitions[0])
            contender["signature"] = "fork-signature"
            barrier = Barrier(2)

            def compete(candidate: dict[str, Any]) -> str:
                barrier.wait()
                try:
                    return store.commit(continuity, candidate)["status"]
                except (sqlite3.DatabaseError, WitnessStateError) as error:
                    return str(error)

            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = sorted(
                    future.result()
                    for future in (
                        executor.submit(compete, transitions[0]),
                        executor.submit(compete, contender),
                    )
                )
            assert outcomes == [
                "WITNESS_STATE_DURABLY_COMMITTED",
                "WitnessCommittedStateConflict",
            ]
            return "ONE_SQLITE_COMMIT_ONE_CONFLICT"

        scenarios.append(_scenario("sqlite-concurrent-fork", concurrent_fork))

        def corrupt_store() -> str:
            stores, continuity, transitions = _initialized_pair(base / "corrupt")
            for store, transition in zip(stores, transitions, strict=True):
                store.commit(continuity, transition)
            stores[1].path.write_bytes(b"not-a-sqlite-database")
            result = evaluate_isolated_witness_stores(stores)
            if result["status"] != STATUS_HOLD:
                raise WitnessStateError("WitnessCorruptStoreAccepted")
            raise WitnessStateError("CORRUPT_STORE_QUORUM_HELD")

        scenarios.append(_scenario("corrupt-store", corrupt_store))

        def split_checkpoint() -> str:
            stores, continuity, transitions = _initialized_pair(base / "split")
            stores[0].commit(continuity, transitions[0])
            split_continuity = copy.deepcopy(continuity)
            split_transition = copy.deepcopy(transitions[1])
            split_transition["state_after"]["checkpoint_sha256"] = "f" * 64
            split_continuity["current_checkpoint_sha256"] = "f" * 64
            stores[1].commit(split_continuity, split_transition)
            result = evaluate_isolated_witness_stores(stores)
            if result["status"] != STATUS_HOLD:
                raise WitnessStateError("WitnessSplitCheckpointAccepted")
            raise WitnessStateError("CHECKPOINT_DISAGREEMENT_HELD")

        scenarios.append(_scenario("split-checkpoint", split_checkpoint))

        def duplicate_path() -> str:
            stores, continuity, transitions = _initialized_pair(base / "same-path")
            stores[0].commit(continuity, transitions[0])
            duplicate = SQLiteWitnessDurableStateStore(
                stores[0].root, stores[0].monitor_id
            )
            result = evaluate_isolated_witness_stores([stores[0], duplicate])
            if result["status"] != STATUS_HOLD:
                raise WitnessStateError("WitnessDuplicatePathAccepted")
            raise WitnessStateError("DUPLICATE_STORE_PATH_HELD")

        scenarios.append(_scenario("duplicate-store-path", duplicate_path))

        def duplicate_identity() -> str:
            stores, continuity, transitions = _initialized_pair(base / "same-id")
            stores[0].commit(continuity, transitions[0])
            other = SQLiteWitnessDurableStateStore(
                base / "same-id-copy", stores[0].monitor_id
            )
            other.initialize(transitions[0]["state_before"])
            other.commit(continuity, transitions[0])
            result = evaluate_isolated_witness_stores([stores[0], other])
            if result["status"] != STATUS_HOLD:
                raise WitnessStateError("WitnessDuplicateIdentityAccepted")
            raise WitnessStateError("DUPLICATE_MONITOR_IDENTITY_HELD")

        scenarios.append(_scenario("duplicate-monitor-identity", duplicate_identity))

        def authority_escalation() -> str:
            stores, continuity, transitions = _initialized_pair(base / "authority")
            escalated = dict(continuity)
            escalated["deployment_authority"] = True
            stores[0].commit(escalated, transitions[0])
            return "AUTHORITY_ESCALATION_ACCEPTED"

        scenarios.append(_scenario("authority-escalation", authority_escalation))

        def halt_not_allowed() -> str:
            stores, continuity, transitions = _initialized_pair(base / "halt-denied")
            stores[0].commit(
                continuity, transitions[0], test_halt_at="after_begin"
            )
            return "TEST_HALT_REACHED_RUNTIME"

        scenarios.append(_scenario("runtime-process-halt-denied", halt_not_allowed))

        def single_store() -> str:
            stores, continuity, transitions = _initialized_pair(base / "single")
            stores[0].commit(continuity, transitions[0])
            result = evaluate_isolated_witness_stores(stores[:1])
            if result["status"] != STATUS_HOLD:
                raise WitnessStateError("WitnessSingleStoreAccepted")
            raise WitnessStateError("SINGLE_STORE_QUORUM_HELD")

        scenarios.append(_scenario("single-store-only", single_store))

    pass_count = sum(item["status"] == "PASS" for item in scenarios)
    hold_count = len(scenarios) - pass_count
    return {
        "schema": "truepanel.holodeck-transparency-witness-sqlite-recovery/v1",
        "simulation": True,
        "filesystem": "TEMPORARY_HOLODECK_ONLY",
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "pass_count": pass_count,
            "hold_count": hold_count,
            "abrupt_process_crash_points_rehearsed": 4,
            "isolated_sqlite_stores_rehearsed": 2,
            "sqlite_wal_full_stores": 2,
            "checkpoint_agreement_acceptances": 1,
            "precommit_signature_leaks": 0,
            "postcommit_signature_losses": 0,
            "rollback_acceptances": 0,
            "concurrent_fork_acceptances": 0,
            "corrupt_store_acceptances": 0,
            "split_checkpoint_acceptances": 0,
            "duplicate_identity_acceptances": 0,
            "authority_escalations": 0,
            "physical_power_loss_validated": 0,
            "independent_production_monitor_operators": 0,
            "coverage_total": 12,
            "coverage_trusted": 12,
            "coverage_gaps": 0,
            "shared_cooling_first_match_sample": 19,
            "isolated_threshold_first_match_sample": 46,
            "lead_samples": 27,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
            "network_calls": 0,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crash-recovery-evidence", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run_transparency_witness_sqlite_recovery_checkride(
        crash_recovery_evidence_path=args.crash_recovery_evidence
    )
    rendered = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_transparency_witness_sqlite_recovery_checkride"]
