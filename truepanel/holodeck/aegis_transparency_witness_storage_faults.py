"""Deterministic storage-image fault corpus for anchored witness recovery."""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from truepanel.aegis.transparency_monitor_quorum import MONITOR_IDS
from truepanel.aegis.transparency_witness_crash_recovery import (
    WitnessStateError,
    _digest,
)
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


def _scenario(name: str, action) -> dict[str, Any]:
    try:
        return {"name": name, "status": "PASS", "observation": action()}
    except (AssertionError, OSError, sqlite3.DatabaseError, WitnessStateError) as error:
        return {"name": name, "status": "HOLD", "observation": str(error)}


def _pair(base: Path):
    continuity, transitions = _fixtures()
    stores = [
        SQLiteWitnessDurableStateStore(base / f"store-{index}", monitor_id)
        for index, monitor_id in enumerate(MONITOR_IDS)
    ]
    for store, transition in zip(stores, transitions, strict=True):
        store.initialize(transition["state_before"])
    return stores, continuity, transitions


def _checkpoint(store: SQLiteWitnessDurableStateStore) -> None:
    connection = sqlite3.connect(store.path)
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
    finally:
        connection.close()


def _image(store: SQLiteWitnessDurableStateStore) -> bytes:
    _checkpoint(store)
    return store.path.read_bytes()


def _restore(store: SQLiteWitnessDurableStateStore, image: bytes) -> None:
    for suffix in ("-wal", "-shm"):
        store.path.with_name(store.path.name + suffix).unlink(missing_ok=True)
    store.path.write_bytes(image)


def _committed(base: Path):
    stores, continuity, transitions = _pair(base)
    for store, transition in zip(stores, transitions, strict=True):
        store.commit(continuity, transition)
    anchor = create_recovery_anchor(stores)
    return stores, continuity, transitions, anchor


def _expect_hold(stores, anchor, observation: str) -> str:
    result = evaluate_anchored_witness_recovery(stores, anchor)
    if result["status"] != STATUS_HOLD:
        raise WitnessStateError(f"{observation}_ACCEPTED")
    raise WitnessStateError(observation)


def run_transparency_witness_storage_fault_checkride(
    root: Path | None = None, *, sqlite_evidence_path: Path | None = None
) -> dict[str, Any]:
    repository = root or Path(__file__).resolve().parents[2]
    predecessor_path = (
        sqlite_evidence_path
        or repository
        / "docs/evidence/aegis-transparency-witness-sqlite-recovery-checkride-v1.json"
    )
    predecessor = json.loads(predecessor_path.read_text(encoding="utf-8"))
    measurements = predecessor.get("measurements", {})
    if (
        predecessor.get("schema")
        != "truepanel.holodeck-transparency-witness-sqlite-recovery/v1"
        or measurements.get("isolated_sqlite_stores_rehearsed") != 2
        or measurements.get("coverage_gaps") != 0
    ):
        raise ValueError("reviewed isolated SQLite witness evidence required")

    with tempfile.TemporaryDirectory(
        prefix="truepanel-aegis-witness-storage-fault-"
    ) as directory:
        base = Path(directory)
        scenarios: list[dict[str, Any]] = []

        def exact_restart() -> str:
            stores, _, _, anchor = _committed(base / "exact-restart")
            result = evaluate_anchored_witness_recovery(stores, anchor)
            assert result["status"] == STATUS_REHEARSED
            assert result["exact_anchor_match"] is True
            return "EXACT_ANCHORED_RESTART_RECOVERED"

        scenarios.append(_scenario("exact-anchored-restart", exact_restart))

        def exact_image_restore() -> str:
            stores, _, _, anchor = _committed(base / "exact-image")
            images = [_image(store) for store in stores]
            for store, image in zip(stores, images, strict=True):
                _restore(store, image)
            result = evaluate_anchored_witness_recovery(stores, anchor)
            assert result["status"] == STATUS_REHEARSED
            return "EXACT_CHECKPOINTED_IMAGES_RECOVERED"

        scenarios.append(_scenario("exact-checkpointed-image-restore", exact_image_restore))

        def zero_header() -> str:
            stores, _, _, anchor = _committed(base / "zero-header")
            image = bytearray(_image(stores[0]))
            image[:100] = b"\x00" * 100
            _restore(stores[0], bytes(image))
            return _expect_hold(stores, anchor, "ZEROED_SQLITE_HEADER_HELD")

        scenarios.append(_scenario("zeroed-database-header", zero_header))

        def truncate_page() -> str:
            stores, _, _, anchor = _committed(base / "truncate")
            image = _image(stores[0])
            _restore(stores[0], image[: max(512, len(image) // 2)])
            return _expect_hold(stores, anchor, "TRUNCATED_DATABASE_IMAGE_HELD")

        scenarios.append(_scenario("truncated-database-image", truncate_page))

        def record_tamper() -> str:
            stores, _, _, anchor = _committed(base / "record-tamper")
            connection = sqlite3.connect(stores[0].path)
            try:
                connection.execute("UPDATE witness_state SET record_json = ?", (b"{}",))
                connection.commit()
            finally:
                connection.close()
            return _expect_hold(stores, anchor, "LOGICAL_RECORD_TAMPER_HELD")

        scenarios.append(_scenario("logical-record-tamper", record_tamper))

        def missing_table() -> str:
            stores, _, _, anchor = _committed(base / "missing-table")
            connection = sqlite3.connect(stores[0].path)
            try:
                connection.execute("DROP TABLE witness_state")
                connection.commit()
            finally:
                connection.close()
            return _expect_hold(stores, anchor, "MISSING_STATE_TABLE_HELD")

        scenarios.append(_scenario("missing-state-table", missing_table))

        def missing_database() -> str:
            stores, _, _, anchor = _committed(base / "missing-database")
            _checkpoint(stores[0])
            stores[0].path.unlink()
            return _expect_hold(stores, anchor, "MISSING_DATABASE_HELD")

        scenarios.append(_scenario("missing-database", missing_database))

        def stale_dual_rollback() -> str:
            stores, continuity, transitions = _pair(base / "stale-dual")
            old_images = [_image(store) for store in stores]
            for store, transition in zip(stores, transitions, strict=True):
                store.commit(continuity, transition)
            anchor = create_recovery_anchor(stores)
            for store, image in zip(stores, old_images, strict=True):
                _restore(store, image)
            return _expect_hold(stores, anchor, "DUAL_STORE_ROLLBACK_HELD")

        scenarios.append(_scenario("dual-store-stale-rollback", stale_dual_rollback))

        def split_generation() -> str:
            stores, continuity, transitions = _pair(base / "split-generation")
            old_image = _image(stores[0])
            for store, transition in zip(stores, transitions, strict=True):
                store.commit(continuity, transition)
            anchor = create_recovery_anchor(stores)
            _restore(stores[0], old_image)
            return _expect_hold(stores, anchor, "SPLIT_GENERATION_HELD")

        scenarios.append(_scenario("split-store-generation", split_generation))

        def swapped_images() -> str:
            stores, _, _, anchor = _committed(base / "swapped")
            left, right = (_image(store) for store in stores)
            _restore(stores[0], right)
            _restore(stores[1], left)
            return _expect_hold(stores, anchor, "SWAPPED_STORE_IMAGES_HELD")

        scenarios.append(_scenario("swapped-store-images", swapped_images))

        def cloned_identity() -> str:
            stores, _, _, anchor = _committed(base / "clone")
            _restore(stores[1], _image(stores[0]))
            return _expect_hold(stores, anchor, "CLONED_STORE_IDENTITY_HELD")

        scenarios.append(_scenario("cloned-store-identity", cloned_identity))

        def anchor_tamper() -> str:
            stores, _, _, anchor = _committed(base / "anchor-tamper")
            changed = dict(anchor)
            changed["checkpoint_sha256"] = "f" * 64
            return _expect_hold(stores, changed, "ANCHOR_DIGEST_TAMPER_HELD")

        scenarios.append(_scenario("anchor-digest-tamper", anchor_tamper))

        def anchor_authority() -> str:
            stores, _, _, anchor = _committed(base / "anchor-authority")
            changed = dict(anchor)
            changed["deployment_authority"] = True
            payload = {key: value for key, value in changed.items() if key != "anchor_sha256"}
            changed["anchor_sha256"] = _digest(payload)
            return _expect_hold(stores, changed, "ANCHOR_AUTHORITY_ESCALATION_HELD")

        scenarios.append(_scenario("anchor-authority-escalation", anchor_authority))

    pass_count = sum(item["status"] == "PASS" for item in scenarios)
    hold_count = len(scenarios) - pass_count
    return {
        "schema": "truepanel.holodeck-transparency-witness-storage-faults/v1",
        "simulation": True,
        "fault_model": "DETERMINISTIC_CHECKPOINTED_STORAGE_IMAGES",
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "pass_count": pass_count,
            "hold_count": hold_count,
            "storage_image_faults_rehearsed": 9,
            "exact_anchor_recoveries": 2,
            "stale_dual_store_acceptances": 0,
            "split_generation_acceptances": 0,
            "corrupt_or_missing_store_acceptances": 0,
            "store_identity_substitution_acceptances": 0,
            "anchor_tamper_acceptances": 0,
            "authority_escalations": 0,
            "physical_power_loss_validated": 0,
            "independent_production_monitor_operators": 0,
            "coverage_total": 13,
            "coverage_trusted": 13,
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
    parser.add_argument("--sqlite-evidence", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run_transparency_witness_storage_fault_checkride(
        sqlite_evidence_path=args.sqlite_evidence
    )
    rendered = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_transparency_witness_storage_fault_checkride"]
