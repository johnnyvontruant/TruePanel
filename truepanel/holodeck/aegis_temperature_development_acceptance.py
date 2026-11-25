"""Adversarial rehearsal for development-only temperature acceptance."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from truepanel.aegis.coverage import coverage_matrix
from truepanel.aegis.rehearsal import rehearse_recovery_paths
from truepanel.aegis.temperature_coverage import (
    build_temperature_coverage_candidate,
    rehearse_temperature_coverage,
)
from truepanel.aegis.temperature_coverage_appraisal import (
    appraise_temperature_coverage,
    temperature_coverage_implementation_sha256,
)
from truepanel.aegis.temperature_development_acceptance import (
    CONFIRMATION_SCHEMA,
    OPERATOR_ID,
    REQUIRED_STATEMENT,
    SCOPE,
    evaluate_temperature_development_acceptance,
    prepare_temperature_development_acceptance,
)
from truepanel.holodeck.aegis_temperature_blind_spot import (
    run_temperature_blind_spot_checkride,
)


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def run_temperature_development_acceptance_checkride() -> dict[str, Any]:
    accepted = coverage_matrix(rehearse_recovery_paths())
    candidate = build_temperature_coverage_candidate(
        accepted, rehearse_temperature_coverage()
    )
    evidence = run_temperature_blind_spot_checkride()
    appraisal = appraise_temperature_coverage(
        accepted,
        candidate,
        evidence,
        implementation_sha256=temperature_coverage_implementation_sha256(
            run_temperature_blind_spot_checkride
        ),
    )
    request = prepare_temperature_development_acceptance(candidate, appraisal)
    confirmation = {
        "schema": CONFIRMATION_SCHEMA,
        "operator_id": OPERATOR_ID,
        "scope": SCOPE,
        "statement": REQUIRED_STATEMENT,
        "subjects": request["subjects"],
        "issued_at": "2026-10-10T04:00:00Z",
        "expires_at": "2026-10-11T04:00:00Z",
    }
    now = "2026-10-10T04:30:00Z"

    cases: list[
        tuple[str, dict[str, Any], dict[str, Any], dict[str, Any] | None, str]
    ] = [
        ("operator-confirmation-absent", candidate, appraisal, None, now),
        ("exact-development-confirmation", candidate, appraisal, confirmation, now),
    ]

    wrong_operator = deepcopy(confirmation)
    wrong_operator["operator_id"] = "vega"
    cases.append(
        ("vega-is-not-human-authority", candidate, appraisal, wrong_operator, now)
    )
    wrong_scope = deepcopy(confirmation)
    wrong_scope["scope"] = "production"
    cases.append(("authority-escalation", candidate, appraisal, wrong_scope, now))
    wrong_statement = deepcopy(confirmation)
    wrong_statement["statement"] = "Looks good."
    cases.append(("ambiguous-statement", candidate, appraisal, wrong_statement, now))
    stale = deepcopy(confirmation)
    stale["issued_at"] = "2026-10-08T04:00:00Z"
    stale["expires_at"] = "2026-10-09T04:00:00Z"
    cases.append(("expired-confirmation", candidate, appraisal, stale, now))
    extended = deepcopy(confirmation)
    extended["note"] = "trust me"
    cases.append(("unknown-confirmation-field", candidate, appraisal, extended, now))
    substituted = deepcopy(confirmation)
    substituted["subjects"] = dict(substituted["subjects"])
    substituted["subjects"]["candidate_document_sha256"] = "0" * 64
    cases.append(("candidate-substitution", candidate, appraisal, substituted, now))
    drifted_appraisal = deepcopy(appraisal)
    drifted_appraisal["coverage"]["candidate"] = "9/9 claimed"
    cases.append(("appraisal-drift", candidate, drifted_appraisal, confirmation, now))
    self_accepted = deepcopy(candidate)
    self_accepted["accepted"] = True
    cases.append(
        ("candidate-self-acceptance", self_accepted, appraisal, confirmation, now)
    )
    long_window = deepcopy(confirmation)
    long_window["expires_at"] = "2026-10-12T04:00:01Z"
    cases.append(("overlong-validity", candidate, appraisal, long_window, now))

    scenarios = []
    results = []
    for name, candidate_value, appraisal_value, confirmation_value, clock in cases:
        result = evaluate_temperature_development_acceptance(
            candidate_value, appraisal_value, confirmation_value, now_utc=clock
        )
        results.append(result)
        scenarios.append(
            {
                "scenario": name,
                "status": result["status"],
                "error_count": len(result["errors"]),
            }
        )

    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0024",
        "scenario": "aegis-temperature-development-acceptance",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "control_authority": False,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "action_required_count": sum(
                r["status"] == "ACTION_REQUIRED_OPERATOR_CONFIRMATION" for r in results
            ),
            "development_accepted_count": sum(
                r["status"] == "DEVELOPMENT_ACCEPTED_FOR_REVIEW" for r in results
            ),
            "hold_count": sum(r["status"] == "HOLD" for r in results),
            "runtime_acceptances": 0,
            "candidate_installations": 0,
            "production_authorizations": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
        },
        "acceptance_request": request,
        "fixture_record": results[1],
    }
    report["evidence_sha256"] = _sha256(report)
    return report


__all__ = ["run_temperature_development_acceptance_checkride"]
