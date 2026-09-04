"""Deterministic AIRWORTHINESS envelope rehearsal."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from truepanel.aegis.assurance import evaluate_airworthiness, load_assurance_envelope
from truepanel.aegis.coverage import coverage_matrix
from truepanel.aegis.policy import DEFAULT_CORRELATION_POLICY
from truepanel.aegis.rehearsal import rehearse_recovery_paths

REHEARSAL_TIMESTAMP = datetime(2026, 9, 3, 12, 0, tzinfo=UTC).timestamp()


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def run_airworthiness_rehearsal() -> dict[str, Any]:
    """Exercise the accepted path and every independent drift class."""

    envelope = load_assurance_envelope()
    matrix = coverage_matrix(rehearse_recovery_paths())
    policy = DEFAULT_CORRELATION_POLICY.describe()
    payload = {"system": {"truenas_version": "25.10.5"}}

    scenarios: list[dict[str, Any]] = []

    def run(
        name: str,
        *,
        candidate_payload: dict[str, Any] | None = None,
        candidate_matrix: dict[str, Any] | None = None,
        candidate_policy: dict[str, Any] | None = None,
        candidate_envelope: dict[str, Any] | None = None,
        now: float = REHEARSAL_TIMESTAMP,
    ) -> None:
        result = evaluate_airworthiness(
            payload=candidate_payload or payload,
            coverage_matrix=candidate_matrix or matrix,
            correlation_policy=candidate_policy or policy,
            envelope=candidate_envelope or envelope,
            now=now,
        )
        scenarios.append(
            {
                "scenario": name,
                "status": result["status"],
                "reason": result["reason"],
                "control_authority": result["control_authority"],
                "production_mutation": result["production_mutation"],
            }
        )

    run("accepted-envelope")
    run("platform-unobserved", candidate_payload={"system": {}})
    run(
        "platform-drift",
        candidate_payload={"system": {"truenas_version": "26.0.0"}},
    )
    run(
        "policy-drift",
        candidate_policy={"policy_id": "unreviewed-policy"},
    )
    incomplete = deepcopy(matrix)
    incomplete["gaps"] = 1
    incomplete["trusted"] = max(0, int(incomplete["total"]) - 1)
    run("coverage-drift", candidate_matrix=incomplete)
    altered = deepcopy(envelope)
    altered["subjects"][0]["sha256"] = "0" * 64
    run("subject-digest-drift", candidate_envelope=altered)
    run("expired-envelope", now=datetime(2027, 1, 1, tzinfo=UTC).timestamp())
    run("clock-rollback", now=datetime(2026, 1, 1, tzinfo=UTC).timestamp())

    statuses = {name: 0 for name in ("CURRENT", "REVIEW", "HOLD")}
    for scenario in scenarios:
        statuses[scenario["status"]] += 1
    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0020",
        "scenario": "aegis-airworthiness-envelope-v1",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "control_authority": False,
        "subjects_checked": len(envelope["subjects"]),
        "evidence_subjects_checked_by_ci": len(envelope["evidence_subjects"]),
        "status_counts": statuses,
        "scenarios": scenarios,
    }
    report["evidence_sha256"] = _digest(report)
    return report


__all__ = ["run_airworthiness_rehearsal"]
