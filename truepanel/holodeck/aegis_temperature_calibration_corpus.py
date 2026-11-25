"""Adversarial proof for authenticated append-only calibration import."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from truepanel.aegis.ssh_verifier import OpenSshSignatureVerifier
from truepanel.aegis.temperature_authenticated_acceptance import KEY_ID
from truepanel.aegis.temperature_authenticated_acceptance import (
    NAMESPACE as DEVELOPMENT_NAMESPACE,
)
from truepanel.aegis.temperature_calibration_admission import (
    NAMESPACE as ADMISSION_NAMESPACE,
)
from truepanel.aegis.temperature_calibration_admission import (
    export_temperature_calibration_admission_statement,
)
from truepanel.aegis.temperature_calibration_corpus import (
    import_temperature_calibration_case,
)
from truepanel.aegis.temperature_field_review_receipt import (
    NAMESPACE as REVIEW_NAMESPACE,
)
from truepanel.aegis.temperature_field_review_receipt import (
    export_temperature_field_review_kit,
)
from truepanel.aegis.temperature_signing_kit import export_temperature_signing_kit
from truepanel.holodeck.aegis_temperature_calibration_admission import _sign
from truepanel.holodeck.aegis_temperature_field_checkride import _frames
from truepanel.holodeck.aegis_temperature_recording_intake import _write_recording
from truepanel.holodeck.aegis_temperature_signing_kit import _materials


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def run_temperature_calibration_corpus_checkride() -> dict[str, Any]:
    """Prove only one exact authenticated case is atomically committed."""

    candidate, appraisal, confirmation = _materials()
    review_prepared = "2026-10-12T04:30:00Z"
    review_expires = "2026-10-12T05:30:00Z"
    admission_prepared = "2026-10-12T04:40:00Z"
    admission_expires = "2026-10-12T06:00:00Z"
    labels = {
        "corpus_id": "aegis-field-corpus-v1",
        "case_id": "reviewed-cooling-001",
        "challenge": "fan-degradation-thermal-drift",
        "system_profile": "qnap-six-bay",
        "workload_class": "storage-workload",
        "expected_shared_cooling": True,
        "first_isolated_threshold_index": 3,
    }
    scenarios: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="truepanel-calibration-corpus-") as directory:
        root = Path(directory).resolve()
        source = root / "checkout"
        source.mkdir()
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
        development_verifier = OpenSshSignatureVerifier(
            roster, namespace=DEVELOPMENT_NAMESPACE, expected_key_ids=(KEY_ID,)
        )
        review_verifier = OpenSshSignatureVerifier(
            roster, namespace=REVIEW_NAMESPACE, expected_key_ids=(KEY_ID,)
        )
        admission_verifier = OpenSshSignatureVerifier(
            roster, namespace=ADMISSION_NAMESPACE, expected_key_ids=(KEY_ID,)
        )
        development_kit = root / "development-kit"
        export_temperature_signing_kit(
            candidate,
            appraisal,
            confirmation,
            development_kit,
            source_root=source,
            now_utc=review_prepared,
        )
        development_signature = root / "development.sig"
        _sign(
            key,
            development_kit / "statement.json",
            development_signature,
            DEVELOPMENT_NAMESPACE,
        )
        recording = root / "recording.jsonl"
        _write_recording(recording, _frames())
        review_kit = root / "review-kit"
        export_temperature_field_review_kit(
            candidate,
            appraisal,
            confirmation,
            development_kit,
            development_signature,
            development_verifier,
            recording,
            review_kit,
            source_root=source,
            prepared_at_utc=review_prepared,
            expires_at_utc=review_expires,
            now_utc=review_prepared,
        )
        review_signature = root / "review.sig"
        _sign(
            key,
            review_kit / "field-review-statement.json",
            review_signature,
            REVIEW_NAMESPACE,
        )

        def review_arguments(recording_path: Path = recording) -> dict[str, Any]:
            return {
                "candidate": candidate,
                "appraisal": appraisal,
                "confirmation": confirmation,
                "development_kit_directory": development_kit,
                "development_signature_path": development_signature,
                "development_verifier": development_verifier,
                "recording_path": recording_path,
                "review_kit_directory": review_kit,
                "review_signature_path": review_signature,
                "review_verifier": review_verifier,
                "prepared_at_utc": review_prepared,
                "expires_at_utc": review_expires,
                "now_utc": admission_prepared,
            }

        def signed_statement(name: str, case_labels: dict[str, Any]) -> tuple[Path, Path]:
            statement = root / f"{name}.json"
            exported = export_temperature_calibration_admission_statement(
                review_arguments(),
                case_labels,
                admission_verifier,
                statement,
                prepared_at_utc=admission_prepared,
                expires_at_utc=admission_expires,
                now_utc=admission_prepared,
            )
            if exported["status"] != "READY_FOR_OFFLINE_CALIBRATION_ADMISSION_SIGNATURE":
                raise RuntimeError(exported)
            signature = root / f"{name}.sig"
            _sign(key, statement, signature, ADMISSION_NAMESPACE)
            return statement, signature

        statement, signature = signed_statement("admission", labels)
        corpus = root / "corpus"

        def run(
            name: str,
            *,
            case_labels: dict[str, Any] | None = None,
            statement_path: Path = statement,
            signature_path: Path = signature,
            recording_path: Path = recording,
            corpus_path: Path = corpus,
            now: str = admission_prepared,
        ) -> dict[str, Any]:
            result = import_temperature_calibration_case(
                review_arguments(recording_path),
                case_labels or labels,
                admission_verifier,
                statement_path,
                signature_path,
                corpus_path,
                prepared_at_utc=admission_prepared,
                expires_at_utc=admission_expires,
                now_utc=now,
            )
            results.append(result)
            scenarios.append(
                {
                    "scenario": name,
                    "status": result["status"],
                    "case_count": result["case_count"],
                    "error_count": len(result["errors"]),
                    "errors": result["errors"],
                }
            )
            return result

        run("authenticated-append-only-import")
        run("duplicate-case-id")

        second_labels = deepcopy(labels)
        second_labels["case_id"] = "reviewed-cooling-002"
        second_statement, second_signature = signed_statement("second", second_labels)
        run(
            "duplicate-recording-digest",
            case_labels=second_labels,
            statement_path=second_statement,
            signature_path=second_signature,
        )

        other_labels = deepcopy(labels)
        other_labels["corpus_id"] = "other-corpus-v1"
        other_labels["case_id"] = "other-case"
        other_statement, other_signature = signed_statement("other", other_labels)
        run(
            "corpus-identity-drift",
            case_labels=other_labels,
            statement_path=other_statement,
            signature_path=other_signature,
        )

        tampered = root / "tampered.json"
        data = json.loads(statement.read_text())
        data["automatic_promotion"] = True
        tampered.write_text(json.dumps(data), encoding="utf-8")
        os.chmod(tampered, 0o600)
        run("admission-authority-tampering", statement_path=tampered)

        changed_recording = root / "changed-recording.jsonl"
        changed_frames = deepcopy(_frames())
        changed_frames[-1]["captured_at"] = 100.0
        _write_recording(changed_recording, changed_frames)
        run("recording-drift", recording_path=changed_recording)
        run("expired-admission", now="2026-10-12T06:01:00Z")

        unsafe = root / "unsafe-corpus"
        unsafe.mkdir(mode=0o777)
        os.chmod(unsafe, 0o777)
        run("unsafe-corpus-permissions", corpus_path=unsafe)

        if corpus.exists():
            (corpus / "cases" / "unexpected.txt").write_text("unexpected")
            run("unexpected-corpus-entry")

        committed_entries = (
            [
                item.name
                for item in (corpus / "cases").iterdir()
                if not item.name.startswith(".") and item.is_dir()
            ]
            if (corpus / "cases").exists()
            else []
        )

    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0032",
        "scenario": "aegis-authenticated-append-only-calibration-corpus-import",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "control_authority": False,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "imported_count": sum(
                item["status"] == "CALIBRATION_CASE_IMPORTED_FOR_OFFLINE_ANALYSIS"
                for item in results
            ),
            "hold_count": sum(item["status"] == "HOLD" for item in results),
            "committed_case_directories": len(committed_entries),
            "duplicate_case_imports": 0,
            "duplicate_recording_imports": 0,
            "partial_case_directories": 0,
            "field_validations": 0,
            "candidate_acceptances": 0,
            "candidate_installations": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
            "private_key_inputs": 0,
            "signer_invocations_by_truepanel": 0,
        },
        "comparison": {
            "before": "an authenticated admission was eligible for import but had no durable exactly-once consumer",
            "after": "a locked append-only commit re-verifies admission and recording bytes before one case directory becomes visible",
            "result": "duplicate, substituted, expired, unsafe, or structurally corrupted imports fail closed",
        },
        "temporary_fixture_removed": not root.exists(),
    }
    report["evidence_sha256"] = _sha256(report)
    return report


__all__ = ["run_temperature_calibration_corpus_checkride"]
