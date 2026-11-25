"""Adversarial HoloDeck appraisal of the temperature coverage candidate."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from truepanel.aegis.coverage import coverage_matrix
from truepanel.aegis.rehearsal import rehearse_recovery_paths
from truepanel.aegis.temperature_coverage import (
    build_temperature_coverage_candidate,
    rehearse_temperature_coverage,
)
from truepanel.aegis.temperature_coverage_appraisal import (
    PINNED_SUBJECTS,
    appraise_temperature_coverage,
    temperature_coverage_implementation_sha256,
)
from truepanel.holodeck.aegis_temperature_blind_spot import (
    run_temperature_blind_spot_checkride,
)


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _resign_candidate(candidate: dict[str, Any]) -> None:
    candidate.pop("candidate_sha256", None)
    candidate["candidate_sha256"] = _sha256(candidate)


def _resign_evidence(report: dict[str, Any]) -> None:
    report.pop("evidence_sha256", None)
    report["evidence_sha256"] = _sha256(report)


def run_temperature_coverage_appraisal_checkride() -> dict[str, Any]:
    """Prove exact-subject appraisal and every authority boundary."""

    accepted = coverage_matrix(rehearse_recovery_paths())
    evidence = run_temperature_blind_spot_checkride()
    candidate = build_temperature_coverage_candidate(
        accepted, rehearse_temperature_coverage()
    )
    implementation = temperature_coverage_implementation_sha256(
        run_temperature_blind_spot_checkride
    )

    def evaluate(
        candidate_value: dict[str, Any] | None = None,
        evidence_value: dict[str, Any] | None = None,
        accepted_value: dict[str, Any] | None = None,
        implementation_value: str | None = None,
        pins: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return appraise_temperature_coverage(
            accepted_value or accepted,
            candidate_value or candidate,
            evidence_value or evidence,
            implementation_sha256=implementation_value or implementation,
            pinned_subjects=pins or PINNED_SUBJECTS,
        )

    scenarios: list[dict[str, Any]] = []

    def record(name: str, mutate: Callable[[], dict[str, Any]]) -> None:
        result = mutate()
        scenarios.append(
            {
                "scenario": name,
                "status": result["status"],
                "error_count": len(result["errors"]),
            }
        )

    record("exact-reviewed-subjects", evaluate)

    tampered = deepcopy(candidate)
    tampered["entries"][-1]["coverage_state"] = "TRUSTED-BY-CLAIM"
    _resign_candidate(tampered)
    record("self-consistent-candidate-tamper", lambda: evaluate(tampered))

    predecessor = deepcopy(accepted)
    predecessor["entries"][0]["title"] += " drift"
    record("accepted-predecessor-drift", lambda: evaluate(accepted_value=predecessor))

    evidence_tamper = deepcopy(evidence)
    evidence_tamper["measurements"]["false_overheating_claims"] = 1
    _resign_evidence(evidence_tamper)
    record("self-consistent-evidence-tamper", lambda: evaluate(evidence_value=evidence_tamper))

    substituted = deepcopy(evidence)
    substituted["scenario"] = "unreviewed-substitute"
    _resign_evidence(substituted)
    record("valid-shaped-evidence-substitution", lambda: evaluate(evidence_value=substituted))

    accepted_candidate = deepcopy(candidate)
    accepted_candidate["accepted"] = True
    _resign_candidate(accepted_candidate)
    record("candidate-self-acceptance", lambda: evaluate(accepted_candidate))

    installed_candidate = deepcopy(candidate)
    installed_candidate["installed"] = True
    _resign_candidate(installed_candidate)
    record("candidate-self-installation", lambda: evaluate(installed_candidate))

    extended = deepcopy(candidate)
    extended["review_note"] = "looks safe"
    _resign_candidate(extended)
    record("unknown-candidate-field", lambda: evaluate(extended))

    bad_pins = dict(PINNED_SUBJECTS)
    bad_pins["unreviewed_subject"] = "0" * 64
    record("unknown-pin-field", lambda: evaluate(pins=bad_pins))

    record(
        "implementation-drift",
        lambda: evaluate(implementation_value="0" * 64),
    )

    unsafe_ready = sum(
        scenario["status"] != "HOLD"
        for scenario in scenarios
        if scenario["scenario"] != "exact-reviewed-subjects"
    )
    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0023",
        "scenario": "aegis-temperature-coverage-appraisal",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "control_authority": False,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "review_ready_count": sum(
                item["status"] == "READY_FOR_INDEPENDENT_REVIEW"
                for item in scenarios
            ),
            "hold_count": sum(item["status"] == "HOLD" for item in scenarios),
            "unsafe_ready_count": unsafe_ready,
            "candidate_acceptances": 0,
            "candidate_installations": 0,
            "runtime_writes": 0,
            "hardware_actions": 0,
        },
        "appraisal": evaluate(),
        "reviewed_subjects": dict(PINNED_SUBJECTS),
    }
    report["evidence_sha256"] = _sha256(report)
    return report


__all__ = ["run_temperature_coverage_appraisal_checkride"]
