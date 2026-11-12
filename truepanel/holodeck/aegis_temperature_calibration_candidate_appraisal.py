"""Deterministic rehearsal for the authenticated candidate appraisal."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from truepanel.aegis.ssh_verifier import OpenSshSignatureVerifier
from truepanel.aegis.temperature_authenticated_acceptance import KEY_ID
from truepanel.aegis.temperature_calibration_candidate_appraisal import (
    DECISION_APPROVE,
    DECISION_HOLD,
    NAMESPACE,
    STATUS_APPROVED,
    STATUS_HELD,
    evaluate_temperature_calibration_candidate_appraisal,
    export_temperature_calibration_candidate_appraisal_statement,
)
from truepanel.aegis.temperature_calibration_candidate_dossier import (
    SCHEMA as DOSSIER_SCHEMA,
)
from truepanel.aegis.temperature_calibration_candidate_dossier import (
    STATUS_READY as DOSSIER_READY,
)
from truepanel.holodeck.aegis_temperature_authenticated_label_join import _sign


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _protected(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)
    os.chmod(path, 0o600)


def _dossier() -> dict[str, Any]:
    value = {
        "schema": DOSSIER_SCHEMA,
        "status": DOSSIER_READY,
        "assembled_at_utc": "2026-10-27T04:30:00Z",
        "decision": "ACCEPT_FOR_CALIBRATION_CANDIDATE_REVIEW",
        "subjects": {
            "decision_receipt_sha256": "1" * 64,
            "review_receipt_sha256": "2" * 64,
            "score_receipt_sha256": "3" * 64,
            "score_sha256": "4" * 64,
            "detector_contract_sha256": "5" * 64,
            "recovery_coverage_matrix_sha256": "6" * 64,
            "holodeck_evidence_sha256": "7" * 64,
        },
        "coverage": {"total": 8, "trusted": 8, "gaps": 0},
        "proof": {
            "lead_samples": 27,
            "passing_accepts": 1,
            "failing_accepts": 0,
        },
        "limitations": [
            "development evidence only",
            "manual review required",
            "no field validation",
        ],
        "field_validated": False,
        "production_validated": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "runtime_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "network_authority": False,
        "automatic_promotion": False,
    }
    value["dossier_sha256"] = hashlib.sha256(_canonical(value)).hexdigest()
    return value


def run_temperature_calibration_candidate_appraisal_checkride() -> dict[str, Any]:
    """Prove explicit appraisal never becomes field or deployment authority."""
    prepared = "2026-10-28T04:00:00Z"
    expires = "2026-10-28T06:00:00Z"
    now = "2026-10-28T05:00:00Z"
    scenarios: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix="truepanel-candidate-appraisal-"
    ) as directory:
        root = Path(directory).resolve()
        key = root / "fixture-key"
        subprocess.run(
            ["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
            check=True,
        )
        roster = root / "allowed_signers"
        roster.write_text(
            f"{KEY_ID} {key.with_suffix('.pub').read_text(encoding='ascii')}",
            encoding="ascii",
        )
        os.chmod(roster, 0o600)
        verifier = OpenSshSignatureVerifier(
            roster, namespace=NAMESPACE, expected_key_ids=(KEY_ID,)
        )
        dossier = root / "dossier.json"
        _protected(dossier, _canonical(_dossier()) + b"\n")

        def prepare(
            name: str, decision: str, rationale: str
        ) -> tuple[Path, Path, dict[str, Any]]:
            statement = root / f"{name}.json"
            result = export_temperature_calibration_candidate_appraisal_statement(
                dossier,
                verifier,
                statement,
                decision=decision,
                rationale=rationale,
                prepared_at_utc=prepared,
                expires_at_utc=expires,
                now_utc=now,
            )
            scenarios.append(
                {
                    "scenario": f"{name}-statement",
                    "status": result["status"],
                    "appraisal_recorded": False,
                    "manual_field_checkride_planning_eligible": False,
                    "error_count": len(result["errors"]),
                }
            )
            signature = root / f"{name}.sig"
            if result["statement_created"]:
                _sign(key, statement, signature, NAMESPACE)
            return statement, signature, result

        approve_statement, approve_signature, _ = prepare(
            "approve",
            DECISION_APPROVE,
            "evidence-complete-for-manual-field-checkride-planning",
        )
        approve_registry = root / "approve-registry"
        approve_registry.mkdir(mode=0o700)
        approved = evaluate_temperature_calibration_candidate_appraisal(
            dossier,
            verifier,
            approve_statement,
            approve_signature,
            approve_registry,
            now_utc=now,
        )
        scenarios.append(
            {
                "scenario": "authenticated-approve-for-manual-planning",
                "status": approved["status"],
                "appraisal_recorded": approved["appraisal_recorded"],
                "manual_field_checkride_planning_eligible": approved[
                    "manual_field_checkride_planning_eligible"
                ],
                "error_count": len(approved["errors"]),
            }
        )

        hold_statement, hold_signature, _ = prepare(
            "hold", DECISION_HOLD, "operator-caution"
        )
        hold_registry = root / "hold-registry"
        hold_registry.mkdir(mode=0o700)
        held = evaluate_temperature_calibration_candidate_appraisal(
            dossier,
            verifier,
            hold_statement,
            hold_signature,
            hold_registry,
            now_utc=now,
        )
        scenarios.append(
            {
                "scenario": "authenticated-operator-hold",
                "status": held["status"],
                "appraisal_recorded": held["appraisal_recorded"],
                "manual_field_checkride_planning_eligible": held[
                    "manual_field_checkride_planning_eligible"
                ],
                "error_count": len(held["errors"]),
            }
        )

        def adversarial(
            name: str,
            *,
            dossier_path: Path = dossier,
            statement_path: Path = approve_statement,
            signature_path: Path = approve_signature,
            verifier_value: Any = verifier,
            registry_mode: int = 0o700,
        ) -> None:
            registry = root / f"{name}-registry"
            registry.mkdir(mode=registry_mode)
            result = evaluate_temperature_calibration_candidate_appraisal(
                dossier_path,
                verifier_value,
                statement_path,
                signature_path,
                registry,
                now_utc=now,
            )
            scenarios.append(
                {
                    "scenario": name,
                    "status": result["status"],
                    "appraisal_recorded": result["appraisal_recorded"],
                    "manual_field_checkride_planning_eligible": result[
                        "manual_field_checkride_planning_eligible"
                    ],
                    "error_count": len(result["errors"]),
                }
            )

        wrong_signature = root / "wrong-namespace.sig"
        _sign(key, approve_statement, wrong_signature, "wrong-appraisal-namespace")
        adversarial("wrong-signature-namespace", signature_path=wrong_signature)

        substituted = root / "substituted-dossier.json"
        changed = copy.deepcopy(_dossier())
        changed["subjects"]["detector_contract_sha256"] = "8" * 64
        changed["dossier_sha256"] = hashlib.sha256(
            _canonical({k: v for k, v in changed.items() if k != "dossier_sha256"})
        ).hexdigest()
        _protected(substituted, _canonical(changed) + b"\n")
        adversarial("dossier-substitution", dossier_path=substituted)

        unknown = root / "unknown-field.json"
        statement_value = json.loads(approve_statement.read_text())
        statement_value["extension"] = "forbidden"
        _protected(unknown, _canonical(statement_value))
        unknown_signature = root / "unknown-field.sig"
        _sign(key, unknown, unknown_signature, NAMESPACE)
        adversarial(
            "unknown-statement-field",
            statement_path=unknown,
            signature_path=unknown_signature,
        )

        escalated = root / "authority-escalation.json"
        statement_value = json.loads(approve_statement.read_text())
        statement_value["field_checkride_authority"] = True
        _protected(escalated, _canonical(statement_value))
        escalated_signature = root / "authority-escalation.sig"
        _sign(key, escalated, escalated_signature, NAMESPACE)
        adversarial(
            "authority-escalation",
            statement_path=escalated,
            signature_path=escalated_signature,
        )

        adversarial("unsafe-registry-permissions", registry_mode=0o755)

        duplicate = evaluate_temperature_calibration_candidate_appraisal(
            dossier,
            verifier,
            approve_statement,
            approve_signature,
            approve_registry,
            now_utc=now,
        )
        scenarios.append(
            {
                "scenario": "duplicate-appraisal-replay",
                "status": duplicate["status"],
                "appraisal_recorded": duplicate["appraisal_recorded"],
                "manual_field_checkride_planning_eligible": duplicate[
                    "manual_field_checkride_planning_eligible"
                ],
                "error_count": len(duplicate["errors"]),
            }
        )

        expired = root / "expired.json"
        expired_result = export_temperature_calibration_candidate_appraisal_statement(
            dossier,
            verifier,
            expired,
            decision=DECISION_APPROVE,
            rationale="evidence-complete-for-manual-field-checkride-planning",
            prepared_at_utc=prepared,
            expires_at_utc=expires,
            now_utc="2026-10-28T06:00:00Z",
        )
        scenarios.append(
            {
                "scenario": "expired-appraisal-window",
                "status": expired_result["status"],
                "appraisal_recorded": False,
                "manual_field_checkride_planning_eligible": False,
                "error_count": len(expired_result["errors"]),
            }
        )

        symlink = root / "dossier-link.json"
        symlink.symlink_to(dossier)
        adversarial("symlinked-dossier", dossier_path=symlink)

    approved_count = sum(item["status"] == STATUS_APPROVED for item in scenarios)
    held_count = sum(item["status"] == STATUS_HELD for item in scenarios)
    signing_ready = sum(item["scenario"].endswith("-statement") for item in scenarios)
    hold_count = len(scenarios) - approved_count - held_count - signing_ready
    unsafe_ready = sum(
        item["manual_field_checkride_planning_eligible"]
        and item["scenario"] != "authenticated-approve-for-manual-planning"
        for item in scenarios
    )
    return {
        "schema": "truepanel.holodeck-temperature-calibration-candidate-appraisal/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "signing_ready_count": signing_ready,
            "approved_for_manual_planning_count": approved_count,
            "operator_hold_count": held_count,
            "hold_count": hold_count,
            "coverage_total": 8,
            "coverage_trusted": 8,
            "coverage_gaps": 0,
            "lead_samples": 27,
            "appraisal_registry_writes": approved_count + held_count,
            "field_checkride_authorizations": 0,
            "field_validations": 0,
            "candidate_acceptances": 0,
            "candidate_installations": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "automatic_promotions": 0,
            "unsafe_ready_count": unsafe_ready,
            "fixture_private_keys_created": 1,
            "fixture_private_keys_retained": 0,
        },
        "limitations": [
            "fixture identity only",
            "approval permits planning only and does not authorize a field checkride",
            "no operational authority",
        ],
    }


__all__ = ["run_temperature_calibration_candidate_appraisal_checkride"]
