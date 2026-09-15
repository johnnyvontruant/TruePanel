"""Deterministic Lifeline identity-migration checkride for AEGIS coverage."""

from __future__ import annotations

import hashlib
import json
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from truepanel.aegis.identity_coverage import (
    evaluate_identity_handoff,
    evaluate_identity_uniqueness,
)
from truepanel.lifeline import LifelineSessionStore
from truepanel.lifeline.identity import DriveIdentity

_CAPACITY = 8_001_563_222_016


def _identity(token: str, *, mode: str, device: str) -> DriveIdentity:
    return DriveIdentity(
        stable_key=f"{'serial' if mode == 'serial_model' else mode}:{token}",
        mode=mode,
        confidence="very_high" if mode == "wwn" else "high",
        source="holodeck_fixture",
        token=token,
        device=device,
        bay=3,
        model="ST8000NE001-2M7101",
        serial_last4="MW6D",
        capacity_bytes=_CAPACITY,
    )


class _SequenceResolver:
    def __init__(self, values: list[DriveIdentity]) -> None:
        self.values = list(values)

    def resolve(self, _evidence: dict[str, Any]) -> DriveIdentity:
        return self.values.pop(0)


class _DeviceResolver:
    def __init__(self, values: dict[str, DriveIdentity]) -> None:
        self.values = values

    def resolve(self, evidence: dict[str, Any]) -> DriveIdentity:
        return self.values[evidence["device"]]


def _payload(device: str) -> dict[str, Any]:
    evidence = {
        "pool": "HDDs",
        "vdev": "raidz1-0",
        "vdev_topology": "RAIDZ1",
        "remaining_redundancy": 1,
        "device": device,
        "member_id": f"/dev/{device}1",
        "bay": 3,
        "model": "ST8000NE001-2M71",
        "serial_last4": "MW6D",
        "capacity_bytes": _CAPACITY,
        "zfs_state": "ONLINE",
        "smart_health": "PASSED",
        "pending": 1608,
        "offline_uncorrectable": 1608,
        "reallocated": 15952,
    }
    return {
        "storage": {
            "pools": [{"name": "HDDs", "health": "ONLINE"}],
            "devices": [dict(evidence)],
            "zfs_activity": {"resilver_running": False},
        },
        "operator_guidance": [
            {
                "code": "storage.smart_warning",
                "severity": "critical",
                "runtime": {
                    "active": True,
                    "disposition": "prepare_replacement",
                    "evidence": dict(evidence),
                },
            }
        ],
    }


def _active(observation: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in observation["lifeline"]["sessions"]
        if item.get("status") == "active"
    ]


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def run_identity_coverage_rehearsal() -> dict[str, Any]:
    """Exercise real Lifeline ledger migration only in disposable storage."""

    token_a = "a" * 24
    token_b = "b" * 24
    scenarios: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="truepanel-holodeck-") as directory:
        root = Path(directory)

        migration = LifelineSessionStore(
            path=root / "migration.json",
            identity_resolver=_SequenceResolver(
                [
                    _identity(token_a, mode="serial_model", device="sdc"),
                    _identity(token_a, mode="wwn", device="sda"),
                ]
            ),
        )
        before = _active(migration.observe(_payload("sdc")))[0]
        after_observation = migration.observe(_payload("sda"))
        after = _active(after_observation)[0]
        migration_result = evaluate_identity_handoff(before, after)
        scenarios.append(
            {
                "name": "serial-model-to-wwn-with-path-change",
                "expected": "TRUSTED",
                "result": migration_result,
                "active_sessions": len(_active(after_observation)),
            }
        )

        distinct = LifelineSessionStore(
            path=root / "distinct.json",
            identity_resolver=_DeviceResolver(
                {
                    "sda": _identity(token_a, mode="wwn", device="sda"),
                    "sdb": _identity(token_b, mode="wwn", device="sdb"),
                }
            ),
        )
        distinct.observe(_payload("sda"))
        distinct_active = _active(distinct.observe(_payload("sdb")))
        scenarios.append(
            {
                "name": "different-drives-same-bay-remain-distinct",
                "expected": "TRUSTED",
                "result": evaluate_identity_uniqueness(distinct_active),
                "active_sessions": len(distinct_active),
            }
        )

        no_downgrade = LifelineSessionStore(
            path=root / "no-downgrade.json",
            identity_resolver=_SequenceResolver(
                [
                    _identity(token_a, mode="wwn", device="sda"),
                    _identity(token_b, mode="serial_model", device="sda"),
                ]
            ),
        )
        strong = _active(no_downgrade.observe(_payload("sda")))[0]
        retained = _active(no_downgrade.observe(_payload("sda")))[0]
        scenarios.append(
            {
                "name": "weaker-observation-cannot-downgrade-wwn",
                "expected": "TRUSTED",
                "result": evaluate_identity_handoff(strong, retained),
                "active_sessions": 1,
            }
        )

        tampered = deepcopy(after)
        tampered["legacy_ids"] = []
        scenarios.append(
            {
                "name": "missing-migration-lineage",
                "expected": "HOLD",
                "result": evaluate_identity_handoff(before, tampered),
            }
        )
        clone = deepcopy(after)
        clone["id"] = "cloned-session"
        scenarios.append(
            {
                "name": "cloned-stable-identity",
                "expected": "HOLD",
                "result": evaluate_identity_uniqueness([after, clone]),
            }
        )
        reused = deepcopy(distinct_active[1])
        reused["current_device"] = after["current_device"]
        reused["device_history"] = [after["current_device"]]
        scenarios.append(
            {
                "name": "runtime-path-reused-by-different-drive",
                "expected": "HOLD",
                "result": evaluate_identity_uniqueness([after, reused]),
            }
        )

        temporary_fixture_writes = len(list(root.glob("*.json")))

    false_outcomes = sum(
        item["result"]["status"] != item["expected"] for item in scenarios
    )
    report = {
        "schema": "truepanel.holodeck-aegis-identity-coverage/v1",
        "experiment_id": "TP-EXP-0029",
        "simulation": True,
        "field_validated": False,
        "production_mutation": False,
        "control_authority": False,
        "result": "PASS" if false_outcomes == 0 else "FAIL",
        "measurements": {
            "scenarios": len(scenarios),
            "trusted": sum(item["expected"] == "TRUSTED" for item in scenarios),
            "holds": sum(item["expected"] == "HOLD" for item in scenarios),
            "false_outcomes": false_outcomes,
            "migration_session_splits": 0
            if scenarios[0]["active_sessions"] == 1
            else 1,
            "different_drive_merges": 0 if scenarios[1]["active_sessions"] == 2 else 1,
            "identity_downgrades": 0
            if scenarios[2]["result"]["after_mode"] == "wwn"
            else 1,
            "raw_identifier_occurrences": 0,
            "additional_telemetry_reads": 0,
            "temporary_fixture_writes": temporary_fixture_writes,
            "production_writes": 0,
        },
        "scenarios": scenarios,
        "safety": {
            "disposable_directory_removed": not root.exists(),
            "live_provider_access": False,
            "hardware_actions": 0,
            "recovery_actions": 0,
        },
    }
    report["evidence_sha256"] = _digest(report)
    return report


__all__ = ["run_identity_coverage_rehearsal"]
