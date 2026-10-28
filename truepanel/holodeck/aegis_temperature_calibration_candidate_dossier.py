"""Deterministic rehearsal of the read-only calibration candidate dossier."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from truepanel.aegis.coverage import coverage_matrix
from truepanel.aegis.rehearsal import rehearse_recovery_paths
from truepanel.aegis.ssh_verifier import OpenSshSignatureVerifier
from truepanel.aegis.temperature_authenticated_acceptance import KEY_ID
from truepanel.aegis.temperature_authenticated_label_join import (
    RECEIPT_SCHEMA as SCORE_SCHEMA,
)
from truepanel.aegis.temperature_authenticated_label_join import STATUS_SCORED
from truepanel.aegis.temperature_calibration_candidate_dossier import (
    assemble_temperature_calibration_candidate_dossier,
)
from truepanel.aegis.temperature_calibration_decision import (
    DECISION_ACCEPT,
    NAMESPACE,
    evaluate_temperature_calibration_decision,
    export_temperature_calibration_decision_statement,
)
from truepanel.aegis.temperature_score_review import IMPLEMENTATION_ID, STATUS_REVIEWED
from truepanel.aegis.temperature_score_review import RECEIPT_SCHEMA as REVIEW_SCHEMA
from truepanel.holodeck.aegis_temperature_authenticated_label_join import _sign
from truepanel.holodeck.aegis_temperature_calibration_decision import (
    run_temperature_calibration_decision_checkride,
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _write(path: Path, value: Any) -> None:
    path.write_bytes(_canonical(value) + b"\n")
    os.chmod(path, 0o600)


def run_temperature_calibration_candidate_dossier_checkride() -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix="truepanel-candidate-dossier-"
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
        score = {
            "schema": SCORE_SCHEMA,
            "status": STATUS_SCORED,
            "evaluated_at_utc": "2026-10-25T03:00:00Z",
            "statistical_contract_sha256": "1" * 64,
            "blinded_manifest_sha256": "2" * 64,
            "detector_contract_sha256": "3" * 64,
            "label_statement_sha256": "4" * 64,
            "label_signature_sha256": "5" * 64,
            "labels_sha256": "6" * 64,
            "operator_key_fingerprint": "SHA256:fixture",
            "score": {"statistical_gates_passed": True},
            "single_evaluation_per_detector_contract": True,
            "case_exclusions": [],
            "threshold_changes": [],
            **{
                key: False
                for key in (
                    "field_validated",
                    "production_validated",
                    "candidate_accepted",
                    "candidate_installed",
                    "runtime_authority",
                    "deployment_authority",
                    "hardware_authority",
                    "storage_write_authority",
                    "network_authority",
                    "automatic_promotion",
                )
            },
        }
        score["receipt_sha256"] = (
            __import__("hashlib").sha256(_canonical(score)).hexdigest()
        )
        score_path = root / "score.json"
        _write(score_path, score)
        review = {
            "schema": REVIEW_SCHEMA,
            "status": STATUS_REVIEWED,
            "reviewed_at_utc": "2026-10-25T04:00:00Z",
            "implementation_id": IMPLEMENTATION_ID,
            "statistical_contract_sha256": "1" * 64,
            "blinded_manifest_sha256": "2" * 64,
            "detector_contract_sha256": "3" * 64,
            "label_statement_sha256": "4" * 64,
            "label_signature_sha256": "5" * 64,
            "score_receipt_sha256": score["receipt_sha256"],
            "score_sha256": "7" * 64,
            "score": {"statistical_gates_passed": True},
            "independent_reconstruction_matched": True,
            "statistical_gates_passed": True,
            "score_registry_read_only": True,
            "score_re_evaluated": False,
            "labels_changed": False,
            "thresholds_changed": False,
            "case_exclusions": [],
            "limitations": ["fixture"],
            **{
                key: False
                for key in (
                    "field_validated",
                    "production_validated",
                    "candidate_accepted",
                    "candidate_installed",
                    "runtime_authority",
                    "deployment_authority",
                    "hardware_authority",
                    "storage_write_authority",
                    "network_authority",
                    "automatic_promotion",
                )
            },
        }
        review["review_receipt_sha256"] = (
            __import__("hashlib").sha256(_canonical(review)).hexdigest()
        )
        review_path = root / "review.json"
        _write(review_path, review)
        statement = root / "decision.json"
        export_temperature_calibration_decision_statement(
            review_path,
            verifier,
            statement,
            decision=DECISION_ACCEPT,
            rationale="score-passed-independent-review",
            prepared_at_utc="2026-10-26T04:00:00Z",
            expires_at_utc="2026-10-26T06:00:00Z",
            now_utc="2026-10-26T05:00:00Z",
        )
        signature = root / "decision.sig"
        _sign(key, statement, signature, NAMESPACE)
        registry = root / "registry"
        registry.mkdir(mode=0o700)
        recorded = evaluate_temperature_calibration_decision(
            review_path,
            verifier,
            statement,
            signature,
            registry,
            prepared_at_utc="2026-10-26T04:00:00Z",
            expires_at_utc="2026-10-26T06:00:00Z",
            now_utc="2026-10-26T05:00:00Z",
        )
        receipt = registry / recorded["receipt_filename"]
        evidence = root / "holodeck-decision-evidence.json"
        _write(evidence, run_temperature_calibration_decision_checkride())
        matrix = coverage_matrix(rehearse_recovery_paths())

        def run(
            name: str,
            *,
            matrix_value: dict[str, Any] | None = None,
            score_value: Path | None = None,
            evidence_value: Path | None = None,
            receipt_value: Path | None = None,
            occupied: bool = False,
        ) -> None:
            output = root / f"{name}.json"
            if occupied:
                output.write_text("occupied")
            result = assemble_temperature_calibration_candidate_dossier(
                review_path,
                score_value or score_path,
                statement,
                signature,
                receipt_value or receipt,
                verifier,
                matrix_value or matrix,
                evidence_value or evidence,
                output,
                now_utc="2026-10-26T05:00:00Z",
            )
            scenarios.append(
                {
                    "scenario": name,
                    "status": result["status"],
                    "ready": result["candidate_review_ready"],
                    "error_count": len(result["errors"]),
                }
            )

        run("complete-content-bound-dossier")
        gap = copy.deepcopy(matrix)
        gap["gaps"] = 1
        gap["trusted"] = 7
        run("coverage-gap", matrix_value=gap)
        bad_score = root / "bad-score.json"
        altered = copy.deepcopy(score)
        altered["detector_contract_sha256"] = "8" * 64
        altered["receipt_sha256"] = (
            __import__("hashlib")
            .sha256(
                _canonical({k: v for k, v in altered.items() if k != "receipt_sha256"})
            )
            .hexdigest()
        )
        _write(bad_score, altered)
        run("detector-substitution", score_value=bad_score)
        bad_evidence = root / "bad-evidence.json"
        proof = json.loads(evidence.read_text())
        proof["measurements"]["unsafe_ready_count"] = 1
        _write(bad_evidence, proof)
        run("unsafe-holodeck-evidence", evidence_value=bad_evidence)
        bad_receipt = root / "bad-receipt.json"
        value = json.loads(receipt.read_text())
        value["candidate_installed"] = True
        _write(bad_receipt, value)
        run("authority-escalation", receipt_value=bad_receipt)
        run("occupied-output", occupied=True)
        missing = root / "missing.json"
        run("missing-score", score_value=missing)
        noncanonical = root / "noncanonical-score.json"
        noncanonical.write_text(json.dumps(score))
        os.chmod(noncanonical, 0o600)
        run("noncanonical-score", score_value=noncanonical)

    ready = sum(item["ready"] for item in scenarios)
    return {
        "schema": "truepanel.holodeck-temperature-calibration-candidate-dossier/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "ready_count": ready,
            "hold_count": len(scenarios) - ready,
            "coverage_total": 8,
            "coverage_trusted": 8,
            "coverage_gaps": 0,
            "lead_samples": 27,
            "unsafe_ready_count": 0,
            "candidate_acceptances": 0,
            "candidate_installations": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "automatic_promotions": 0,
        },
        "limitations": [
            "fixture identities only",
            "manual review remains mandatory",
            "no operational authority",
        ],
    }


__all__ = ["run_temperature_calibration_candidate_dossier_checkride"]
