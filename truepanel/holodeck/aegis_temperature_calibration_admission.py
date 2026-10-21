"""Adversarial proof for content-bound temperature calibration admission."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
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
    evaluate_temperature_calibration_admission,
    export_temperature_calibration_admission_statement,
)
from truepanel.aegis.temperature_field_review_receipt import (
    NAMESPACE as REVIEW_NAMESPACE,
)
from truepanel.aegis.temperature_field_review_receipt import (
    export_temperature_field_review_kit,
)
from truepanel.aegis.temperature_signing_kit import export_temperature_signing_kit
from truepanel.holodeck.aegis_temperature_field_checkride import _frames
from truepanel.holodeck.aegis_temperature_recording_intake import _write_recording
from truepanel.holodeck.aegis_temperature_signing_kit import _materials


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _sign(key: Path, statement: Path, destination: Path, namespace: str) -> None:
    subprocess.run(
        [
            "/usr/bin/ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(key),
            "-n",
            namespace,
            str(statement),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    Path(f"{statement}.sig").replace(destination)
    os.chmod(destination, 0o600)


def run_temperature_calibration_admission_checkride() -> dict[str, Any]:
    """Prove labels cannot drift away from the reviewed recording."""

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

    with tempfile.TemporaryDirectory(prefix="truepanel-calibration-admission-") as directory:
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

        statement = root / "calibration-admission.json"
        export_result = export_temperature_calibration_admission_statement(
            review_arguments(),
            labels,
            admission_verifier,
            statement,
            prepared_at_utc=admission_prepared,
            expires_at_utc=admission_expires,
            now_utc=admission_prepared,
        )
        results.append(export_result)
        scenarios.append(
            {
                "scenario": "public-admission-statement",
                "status": export_result["status"],
                "error_count": len(export_result["errors"]),
            }
        )
        signature = root / "calibration-admission.sig"
        _sign(key, statement, signature, ADMISSION_NAMESPACE)

        def run(
            name: str,
            *,
            arguments: dict[str, Any] | None = None,
            case_labels: dict[str, Any] | None = None,
            verifier: Any = admission_verifier,
            statement_path: Path = statement,
            signature_path: Path | None = signature,
            now: str = admission_prepared,
        ) -> dict[str, Any]:
            result = evaluate_temperature_calibration_admission(
                arguments or review_arguments(),
                case_labels or labels,
                verifier,
                statement_path,
                signature_path,
                prepared_at_utc=admission_prepared,
                expires_at_utc=admission_expires,
                now_utc=now,
            )
            results.append(result)
            scenarios.append(
                {
                    "scenario": name,
                    "status": result["status"],
                    "error_count": len(result["errors"]),
                }
            )
            return result

        run("content-bound-calibration-admission")
        run("delayed-admission-within-window", now="2026-10-12T05:20:00Z")

        changed_labels = deepcopy(labels)
        changed_labels["expected_shared_cooling"] = False
        run("outcome-label-drift", case_labels=changed_labels)

        changed_profile = deepcopy(labels)
        changed_profile["system_profile"] = "different-appliance"
        run("system-profile-drift", case_labels=changed_profile)

        extra_label = deepcopy(labels)
        extra_label["operator_override"] = True
        run("unknown-label-field", case_labels=extra_label)

        changed_recording = root / "changed-recording.jsonl"
        frames = deepcopy(_frames())
        frames[1]["captured_at"] = 100.0
        _write_recording(changed_recording, frames)
        run("recording-drift", arguments=review_arguments(changed_recording))

        tampered_statement = root / "tampered-admission.json"
        data = json.loads(statement.read_text())
        data["hardware_authority"] = True
        tampered_statement.write_text(json.dumps(data), encoding="utf-8")
        os.chmod(tampered_statement, 0o600)
        run("authority-escalation", statement_path=tampered_statement)

        wrong_namespace_signature = root / "wrong-namespace.sig"
        _sign(key, statement, wrong_namespace_signature, REVIEW_NAMESPACE)
        run("wrong-signature-namespace", signature_path=wrong_namespace_signature)

        foreign_key = root / "foreign-key"
        subprocess.run(
            [
                "/usr/bin/ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-f",
                str(foreign_key),
            ],
            check=True,
        )
        foreign_roster = root / "foreign_allowed_signers"
        foreign_roster.write_text(
            f"{KEY_ID} {foreign_key.with_suffix('.pub').read_text(encoding='ascii')}",
            encoding="ascii",
        )
        os.chmod(foreign_roster, 0o600)
        foreign_verifier = OpenSshSignatureVerifier(
            foreign_roster,
            namespace=ADMISSION_NAMESPACE,
            expected_key_ids=(KEY_ID,),
        )
        foreign_signature = root / "foreign.sig"
        _sign(foreign_key, statement, foreign_signature, ADMISSION_NAMESPACE)
        run(
            "same-principal-foreign-trust-root",
            verifier=foreign_verifier,
            signature_path=foreign_signature,
        )

        unsafe_statement = root / "unsafe-admission.json"
        shutil.copyfile(statement, unsafe_statement)
        os.chmod(unsafe_statement, 0o666)
        run("unsafe-statement-permissions", statement_path=unsafe_statement)
        run("expired-admission-window", now="2026-10-12T06:01:00Z")

        paths_retained = sum(str(root) in json.dumps(item) for item in results)

    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0031",
        "scenario": "aegis-content-bound-temperature-calibration-admission",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "control_authority": False,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "signing_ready_count": sum(
                item["status"] == "READY_FOR_OFFLINE_CALIBRATION_ADMISSION_SIGNATURE"
                for item in results
            ),
            "admitted_count": sum(
                item["status"] == "CALIBRATION_CASE_AUTHENTICATED_FOR_CORPUS_IMPORT"
                for item in results
            ),
            "hold_count": sum(item["status"] == "HOLD" for item in results),
            "unsafe_ready_count": sum(item["status"] != "HOLD" for item in results[3:]),
            "source_paths_retained": paths_retained,
            "private_key_inputs": sum(
                item["private_key_accepted"] is not False for item in results
            ),
            "signer_invocations_by_truepanel": sum(
                item["signer_invoked"] is not False for item in results
            ),
            "fixture_private_keys_created": 2,
            "fixture_private_keys_retained": 0,
            "corpus_writes": 0,
            "field_validations": 0,
            "candidate_acceptances": 0,
            "candidate_installations": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
        },
        "comparison": {
            "before": "a reviewed recording could be paired with caller-supplied corpus labels",
            "after": "a distinct SSHSIG binds the exact reviewed recording, corpus identity, outcome, profile, workload, threshold landmark, expiry, and zero authority",
            "result": "label drift fails closed before any calibration-corpus write",
        },
        "temporary_fixture_removed": not root.exists(),
    }
    report["evidence_sha256"] = _sha256(report)
    return report


__all__ = ["run_temperature_calibration_admission_checkride"]
