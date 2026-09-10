"""Deterministic upgrade and envelope-renewal rehearsal."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from truepanel.aegis.assurance import evaluate_airworthiness, load_assurance_envelope
from truepanel.aegis.coverage import coverage_matrix
from truepanel.aegis.passive_runtime import BoundedTrueNASQueryCache
from truepanel.aegis.platform_witness import (
    bind_platform_witness,
    issue_platform_witness,
)
from truepanel.aegis.policy import DEFAULT_CORRELATION_POLICY
from truepanel.aegis.rehearsal import rehearse_recovery_paths
from truepanel.aegis.requalification import (
    envelope_sha256,
    evaluate_successor_envelope,
    renewal_contract_sha256,
)

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC).timestamp()


class _Client:
    def __init__(self, version: str) -> None:
        self.version = version

    def call(self, _method: str, *_arguments: Any) -> str:
        return f"TrueNAS-SCALE-{self.version}"


def platform_payload(version: str) -> dict[str, Any]:
    witness = issue_platform_witness(
        BoundedTrueNASQueryCache(_Client(version)),
        clock=lambda: NOW,
    )
    return bind_platform_witness({"system": {}}, witness)


def build_candidate_fixture(
    accepted: dict[str, Any],
    root: Path,
    *,
    version: str = "25.10.6",
) -> dict[str, Any]:
    candidate = deepcopy(accepted)
    candidate.update(
        {
            "envelope_id": "aegis-airworthiness-upgrade-rehearsal-v3",
            "predecessor_envelope_sha256": envelope_sha256(accepted),
            "issued_at": "2026-09-06T04:08:19Z",
            "expires_at": "2026-12-05T04:08:19Z",
            "platform_version": version,
            "review_required": True,
            "automatic_acceptance": False,
            "renewal_contract_sha256": renewal_contract_sha256(root),
        }
    )
    return candidate


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_requalification_rehearsal(
    *, package_root: Path | None = None
) -> dict[str, Any]:
    """Prove old-envelope HOLD and successor review without acceptance."""

    root = package_root or Path(__file__).resolve().parents[1]
    accepted = load_assurance_envelope()
    matrix = coverage_matrix(rehearse_recovery_paths())
    policy = DEFAULT_CORRELATION_POLICY.describe()

    drifted = evaluate_airworthiness(
        payload=platform_payload("25.10.6"),
        coverage_matrix=matrix,
        correlation_policy=policy,
        now=NOW,
        envelope=accepted,
        package_root=root,
    )
    scenarios: list[dict[str, Any]] = []

    def record(
        name: str, candidate: dict[str, Any], version: str, expected: str
    ) -> None:
        result = evaluate_successor_envelope(
            accepted=accepted,
            candidate=candidate,
            payload=platform_payload(version),
            coverage_matrix=matrix,
            correlation_policy=policy,
            now=NOW,
            package_root=root,
        )
        scenarios.append(
            {
                "scenario": name,
                "status": result["status"],
                "reason": result["reason"],
                "transition": result["transition"],
                "expected": expected,
                "candidate_installed": result["candidate_installed"],
                "automatic_acceptance": result["automatic_acceptance"],
                "runtime_writes": result["runtime_writes"],
                "control_authority": result["control_authority"],
            }
        )

    upgrade = build_candidate_fixture(accepted, root)
    record("coherent-upgrade", upgrade, "25.10.6", "READY_FOR_OPERATOR_REVIEW")
    record(
        "same-platform-renewal",
        build_candidate_fixture(accepted, root, version="25.10.5"),
        "25.10.5",
        "READY_FOR_OPERATOR_REVIEW",
    )
    record(
        "prerelease-order-unknown",
        build_candidate_fixture(accepted, root, version="25.10-RC.1"),
        "25.10-RC.1",
        "REVIEW",
    )

    missing_witness = deepcopy(upgrade)
    result = evaluate_successor_envelope(
        accepted=accepted,
        candidate=missing_witness,
        payload={"system": {}},
        coverage_matrix=matrix,
        correlation_policy=policy,
        now=NOW,
        package_root=root,
    )
    scenarios.append(
        {
            "scenario": "platform-witness-missing",
            "status": result["status"],
            "reason": result["reason"],
            "transition": result["transition"],
            "expected": "REVIEW",
            "candidate_installed": result["candidate_installed"],
            "automatic_acceptance": result["automatic_acceptance"],
            "runtime_writes": result["runtime_writes"],
            "control_authority": result["control_authority"],
        }
    )

    wrong_parent = deepcopy(upgrade)
    wrong_parent["predecessor_envelope_sha256"] = "0" * 64
    record("wrong-predecessor", wrong_parent, "25.10.6", "HOLD")
    record(
        "platform-downgrade",
        build_candidate_fixture(accepted, root, version="25.10.4"),
        "25.10.4",
        "HOLD",
    )
    overlong = deepcopy(upgrade)
    overlong["expires_at"] = "2027-09-06T04:08:19Z"
    record("overlong-validity", overlong, "25.10.6", "HOLD")
    automatic = deepcopy(upgrade)
    automatic["automatic_acceptance"] = True
    record("automatic-acceptance", automatic, "25.10.6", "HOLD")
    contract_drift = deepcopy(upgrade)
    contract_drift["renewal_contract_sha256"] = "0" * 64
    record("renewal-contract-drift", contract_drift, "25.10.6", "HOLD")
    subject_drift = deepcopy(upgrade)
    subject_drift["subjects"][0]["sha256"] = "0" * 64
    record("runtime-subject-drift", subject_drift, "25.10.6", "HOLD")

    counts = {
        status: sum(item["status"] == status for item in scenarios)
        for status in ("READY_FOR_OPERATOR_REVIEW", "REVIEW", "HOLD")
    }
    false_ready = sum(item["status"] != item["expected"] for item in scenarios)
    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0022",
        "scenario": "aegis-airworthiness-requalification-v1",
        "simulation": True,
        "hardware_isolated": True,
        "renewal_contract_sha256": renewal_contract_sha256(root),
        "old_envelope_after_upgrade": {
            "status": drifted["status"],
            "reason": drifted["reason"],
        },
        "status_counts": counts,
        "scenarios": scenarios,
        "measurements": {
            "false_review_ready_paths": false_ready,
            "candidate_installations": 0,
            "automatic_acceptances": 0,
            "runtime_writes": 0,
        },
        "production_mutation": False,
        "control_authority": False,
    }
    report["evidence_sha256"] = _digest(report)
    return report


__all__ = [
    "build_candidate_fixture",
    "platform_payload",
    "run_requalification_rehearsal",
]
