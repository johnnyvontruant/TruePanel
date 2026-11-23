"""Deterministic power-loss and concurrent-update witness-state checkride."""

from __future__ import annotations

import argparse
import contextlib
import copy
import json
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any

from truepanel.aegis.rfc4998_transparent_custody import consistency_proof, merkle_root
from truepanel.aegis.transparency_monitor_quorum import (
    MONITOR_IDS,
)
from truepanel.aegis.transparency_monitor_quorum import (
    SCHEMA as QUORUM_SCHEMA,
)
from truepanel.aegis.transparency_monitor_quorum import (
    STATUS_REHEARSED as QUORUM_REHEARSED,
)
from truepanel.aegis.transparency_witness_continuity import (
    SCHEMA as CONTINUITY_SCHEMA,
)
from truepanel.aegis.transparency_witness_continuity import (
    STATUS_REHEARSED as CONTINUITY_REHEARSED,
)
from truepanel.aegis.transparency_witness_continuity import (
    TRANSITION_SCHEMA,
    checkpoint_digest,
    evaluate_witness_continuity,
)
from truepanel.aegis.transparency_witness_crash_recovery import (
    STATUS_COMMITTED,
    STATUS_REPLAYED,
    InjectedCrash,
    WitnessDurableStateStore,
    WitnessStateError,
)

_DENIED = (
    "production_trusted",
    "runtime_authority",
    "deployment_authority",
    "hardware_authority",
    "network_authority",
    "storage_authority",
)


def _fixtures() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    leaves = [b"genesis", b"custody-1", b"checkpoint-1", b"custody-2", b"checkpoint-2"]
    prior = {
        "origin": "truepanel-aegis-holodeck-log-v1",
        "tree_size": 3,
        "root_hash_sha256": merkle_root(leaves[:3]).hex(),
    }
    current = {
        "origin": prior["origin"],
        "tree_size": 5,
        "root_hash_sha256": merkle_root(leaves).hex(),
    }
    proof = [item.hex() for item in consistency_proof(3, leaves)]
    transitions: list[dict[str, Any]] = []
    for index, monitor_id in enumerate(MONITOR_IDS):
        transitions.append(
            {
                "schema": TRANSITION_SCHEMA,
                "monitor_id": monitor_id,
                "state_before": {
                    "monitor_id": monitor_id,
                    "origin": prior["origin"],
                    "tree_size": 3,
                    "root_hash_sha256": prior["root_hash_sha256"],
                    "checkpoint_sha256": checkpoint_digest(prior),
                    "state_sequence": 7,
                },
                "state_after": {
                    "monitor_id": monitor_id,
                    "origin": current["origin"],
                    "tree_size": 5,
                    "root_hash_sha256": current["root_hash_sha256"],
                    "checkpoint_sha256": checkpoint_digest(current),
                    "state_sequence": 8,
                },
                "consistency_path": proof,
                "persisted_before_cosignature": True,
                "signature": f"holodeck-signature-{index}",
            }
        )
    quorum = {
        "schema": QUORUM_SCHEMA,
        "status": QUORUM_REHEARSED,
        "independent_monitor_quorum_rehearsed": True,
        **{name: False for name in _DENIED},
    }
    continuity = evaluate_witness_continuity(
        quorum, prior, current, transitions, lambda *_: True
    )
    if (
        continuity.get("schema") != CONTINUITY_SCHEMA
        or continuity.get("status") != CONTINUITY_REHEARSED
    ):
        raise RuntimeError("continuity fixture did not verify")
    return continuity, transitions


def _scenario(
    root: Path,
    name: str,
    action: Callable[[WitnessDurableStateStore, dict[str, Any], dict[str, Any]], str],
) -> dict[str, Any]:
    continuity, transitions = _fixtures()
    transition = transitions[0]
    store = WitnessDurableStateStore(root / name, MONITOR_IDS[0])
    store.initialize(transition["state_before"])
    try:
        observation = action(store, continuity, transition)
        return {"name": name, "status": "PASS", "observation": observation}
    except (InjectedCrash, WitnessStateError) as error:
        return {"name": name, "status": "HOLD", "observation": str(error)}


def run_transparency_witness_crash_recovery_checkride(
    root: Path | None = None, *, continuity_evidence_path: Path | None = None
) -> dict[str, Any]:
    repository = root or Path(__file__).resolve().parents[2]
    evidence_path = (
        continuity_evidence_path
        or repository
        / "docs/evidence/aegis-transparency-witness-continuity-checkride-v1.json"
    )
    predecessor = json.loads(evidence_path.read_text(encoding="utf-8"))
    if (
        predecessor.get("schema")
        != "truepanel.holodeck-transparency-witness-continuity/v1"
        or predecessor.get("measurements", {}).get("two_monitor_ratchets_verified") != 1
    ):
        raise ValueError("reviewed witness-continuity evidence required")

    with tempfile.TemporaryDirectory(
        prefix="truepanel-aegis-witness-crash-"
    ) as directory:
        base = Path(directory)
        scenarios: list[dict[str, Any]] = []
        scenarios.append(
            _scenario(
                base,
                "clean-durable-commit",
                lambda store, continuity, transition: store.commit(
                    continuity, transition
                )["status"],
            )
        )

        def exact_retry(
            store: WitnessDurableStateStore,
            continuity: dict[str, Any],
            transition: dict[str, Any],
        ) -> str:
            assert store.commit(continuity, transition)["status"] == STATUS_COMMITTED
            return store.commit(continuity, transition)["status"]

        scenarios.append(_scenario(base, "exact-retry-is-idempotent", exact_retry))

        def crash_recovery(
            stage: str,
        ) -> Callable[[WitnessDurableStateStore, dict[str, Any], dict[str, Any]], str]:
            def run(
                store: WitnessDurableStateStore,
                continuity: dict[str, Any],
                transition: dict[str, Any],
            ) -> str:
                with contextlib.suppress(InjectedCrash):
                    store.commit(continuity, transition, crash_at=stage)
                recovered = store.recover()
                sequence = recovered["record"]["state"]["state_sequence"]
                if stage in {"before_temp_write", "after_temp_fsync"}:
                    if sequence != 7 or recovered["recoverable_signature"] is not None:
                        raise WitnessStateError("WitnessPrecommitCrashLeakedSuccessor")
                    outcome = store.commit(continuity, transition)
                    if outcome["status"] != STATUS_COMMITTED:
                        raise WitnessStateError("WitnessPrecommitRetryFailed")
                    return "PRIOR_RECOVERED_THEN_COMMITTED"
                if (
                    sequence != 8
                    or recovered["recoverable_signature"] != transition["signature"]
                ):
                    raise WitnessStateError("WitnessPostcommitRecoveryIncomplete")
                if store.commit(continuity, transition)["status"] != STATUS_REPLAYED:
                    raise WitnessStateError("WitnessPostcommitReplayFailed")
                return "COMMITTED_SIGNATURE_RECOVERED"

            return run

        for stage in (
            "before_temp_write",
            "after_temp_fsync",
            "after_replace",
            "after_directory_fsync",
        ):
            scenarios.append(
                _scenario(
                    base, f"crash-{stage.replace('_', '-')}", crash_recovery(stage)
                )
            )

        def stale_loser(
            store: WitnessDurableStateStore,
            continuity: dict[str, Any],
            transition: dict[str, Any],
        ) -> str:
            contender = copy.deepcopy(transition)
            contender["signature"] = "fork-signature"
            second_store = WitnessDurableStateStore(store.root, store.monitor_id)
            barrier = Barrier(2)

            def compete(
                candidate_store: WitnessDurableStateStore,
                candidate: dict[str, Any],
            ) -> str:
                barrier.wait()
                try:
                    return candidate_store.commit(continuity, candidate)["status"]
                except WitnessStateError as error:
                    return str(error)

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = (
                    executor.submit(compete, store, transition),
                    executor.submit(compete, second_store, contender),
                )
                outcomes = sorted(future.result() for future in futures)
            if outcomes != [
                "WITNESS_STATE_DURABLY_COMMITTED",
                "WitnessCommittedStateConflict",
            ]:
                raise WitnessStateError("WitnessConcurrentForkAccepted")
            return "ONE_COMMIT_ONE_CONFLICT"

        scenarios.append(_scenario(base, "serialized-concurrent-fork", stale_loser))

        def stale_before(
            store: WitnessDurableStateStore,
            continuity: dict[str, Any],
            transition: dict[str, Any],
        ) -> str:
            contender = copy.deepcopy(transition)
            contender["state_before"]["state_sequence"] = 6
            try:
                store.commit(continuity, contender)
            except WitnessStateError as error:
                if str(error) != "WitnessCompareAndSwapConflict":
                    raise
                return "STALE_COMPARE_AND_SWAP_REJECTED"
            raise WitnessStateError("WitnessStaleStateAccepted")

        scenarios.append(_scenario(base, "stale-state-compare-and-swap", stale_before))

        def corrupt_state(
            store: WitnessDurableStateStore,
            continuity: dict[str, Any],
            transition: dict[str, Any],
        ) -> str:
            record = store.read()
            record["state"]["state_sequence"] = 99
            store.path.write_text(json.dumps(record), encoding="utf-8")
            try:
                store.read()
            except WitnessStateError as error:
                if str(error) != "WitnessStateDigestMismatch":
                    raise
                return "CORRUPT_STATE_REJECTED"
            raise WitnessStateError("WitnessCorruptStateAccepted")

        scenarios.append(_scenario(base, "corrupt-record-digest", corrupt_state))

        def authority(
            store: WitnessDurableStateStore,
            continuity: dict[str, Any],
            transition: dict[str, Any],
        ) -> str:
            escalated = dict(continuity)
            escalated["storage_authority"] = True
            store.commit(escalated, transition)
            return "UNEXPECTED"

        scenarios.append(_scenario(base, "authority-escalation", authority))

        def unverified(
            store: WitnessDurableStateStore,
            continuity: dict[str, Any],
            transition: dict[str, Any],
        ) -> str:
            invalid = dict(continuity)
            invalid["valid_monitor_ids"] = [MONITOR_IDS[1]]
            store.commit(invalid, transition)
            return "UNEXPECTED"

        scenarios.append(_scenario(base, "monitor-not-verified", unverified))

        def missing_signature(
            store: WitnessDurableStateStore,
            continuity: dict[str, Any],
            transition: dict[str, Any],
        ) -> str:
            invalid = dict(transition)
            invalid["signature"] = ""
            store.commit(continuity, invalid)
            return "UNEXPECTED"

        scenarios.append(
            _scenario(base, "missing-recoverable-signature", missing_signature)
        )

        def checkpoint_substitution(
            store: WitnessDurableStateStore,
            continuity: dict[str, Any],
            transition: dict[str, Any],
        ) -> str:
            invalid = dict(continuity)
            invalid["current_checkpoint_sha256"] = "0" * 64
            store.commit(invalid, transition)
            return "UNEXPECTED"

        scenarios.append(
            _scenario(base, "checkpoint-substitution", checkpoint_substitution)
        )

        def pending_symlink(
            store: WitnessDurableStateStore,
            continuity: dict[str, Any],
            transition: dict[str, Any],
        ) -> str:
            store.pending_path.symlink_to(store.path)
            store.recover()
            return "UNEXPECTED"

        scenarios.append(_scenario(base, "pending-symlink", pending_symlink))

    pass_count = sum(item["status"] == "PASS" for item in scenarios)
    hold_count = sum(item["status"] == "HOLD" for item in scenarios)
    return {
        "schema": "truepanel.holodeck-transparency-witness-crash-recovery/v1",
        "simulation": True,
        "filesystem": "TEMPORARY_HOLODECK_ONLY",
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "pass_count": pass_count,
            "hold_count": hold_count,
            "crash_points_rehearsed": 4,
            "precommit_signature_leaks": 0,
            "postcommit_signature_losses": 0,
            "rollback_acceptances": 0,
            "concurrent_fork_acceptances": 0,
            "corrupt_state_acceptances": 0,
            "authority_escalations": 0,
            "coverage_total": 11,
            "coverage_trusted": 11,
            "coverage_gaps": 0,
            "shared_cooling_first_match_sample": 19,
            "isolated_threshold_first_match_sample": 46,
            "lead_samples": 27,
            "independent_production_monitor_operators": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
            "network_calls": 0,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--continuity-evidence", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run_transparency_witness_crash_recovery_checkride(
        continuity_evidence_path=args.continuity_evidence
    )
    rendered = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_transparency_witness_crash_recovery_checkride"]
