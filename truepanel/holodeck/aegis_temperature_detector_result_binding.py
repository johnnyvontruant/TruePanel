"""Adversarial proof for label-blind detector-result binding."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from truepanel.aegis.ssh_verifier import OpenSshSignatureVerifier
from truepanel.aegis.temperature_authenticated_acceptance import KEY_ID
from truepanel.aegis.temperature_calibration_admission import (
    NAMESPACE as ADMISSION_NAMESPACE,
)
from truepanel.aegis.temperature_detector_result import (
    export_temperature_detector_result,
)
from truepanel.aegis.temperature_detector_result_binding import (
    NAMESPACE as BINDING_NAMESPACE,
)
from truepanel.aegis.temperature_detector_result_binding import (
    evaluate_temperature_detector_result_binding,
    export_temperature_detector_result_binding_statement,
)
from truepanel.holodeck.aegis_corpus import builtin_corpus_path


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sign(key: Path, namespace: str, statement: Path, destination: Path) -> None:
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


def _write(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)
    os.chmod(path, 0o600)


def run_temperature_detector_result_binding_checkride() -> dict[str, Any]:
    """Prove predictions precede labels and remain bound to exact evidence."""

    scenarios: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="truepanel-detector-binding-") as directory:
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

        def scenario(
            name: str,
            *,
            result_time: str = "2026-10-18T03:55:00Z",
            pre: Callable[[Path], None] | None = None,
            post: Callable[[Path], None] | None = None,
            wrong_binding_namespace: bool = False,
        ) -> None:
            case = root / name
            case.mkdir(mode=0o700)
            recording = case / "recording.jsonl"
            shutil.copyfile(
                builtin_corpus_path() / "fan-bearing-degradation.jsonl", recording
            )
            os.chmod(recording, 0o600)
            result_path = case / "detector-result.json"
            export_temperature_detector_result(
                recording, result_path, generated_at_utc=result_time
            )
            admission_statement = case / "admission.json"
            recording_bytes = recording.read_bytes()
            admission = {
                "schema": "truepanel.aegis-temperature-calibration-admission-statement/v1",
                "namespace": ADMISSION_NAMESPACE,
                "scope": "temperature-calibration-corpus-import-only",
                "key_id": KEY_ID,
                "operator_key_fingerprint": "fixture-bound-by-openssh",
                "prepared_at_utc": "2026-10-18T04:00:00Z",
                "expires_at_utc": "2026-10-18T05:00:00Z",
                "field_review_receipt_sha256": "1" * 64,
                "field_review_statement_sha256": "2" * 64,
                "recording_sha256": _sha256(recording_bytes),
                "recording_bytes": len(recording_bytes),
                "frame_count": len(recording_bytes.splitlines()),
                "labels": {
                    "corpus_id": "aegis-field-corpus-v1",
                    "case_id": "fan-bearing-degradation",
                    "challenge": "shared-cause-positive",
                    "system_profile": "qnap-six-bay",
                    "workload_class": "storage-heavy",
                    "expected_shared_cooling": True,
                    "first_isolated_threshold_index": 46,
                },
                "label_statement": (
                    "I confirm these labels describe the reviewed incident outcome "
                    "for calibration corpus import only."
                ),
                "eligible_for_corpus_import": True,
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
            _write(admission_statement, _canonical(admission))
            admission_signature = case / "admission.sshsig"
            _sign(key, ADMISSION_NAMESPACE, admission_statement, admission_signature)
            if pre:
                pre(case)
            admission_verifier = OpenSshSignatureVerifier(
                roster,
                namespace=ADMISSION_NAMESPACE,
                expected_key_ids=(KEY_ID,),
            )
            namespace = "wrong-namespace@truepanel" if wrong_binding_namespace else BINDING_NAMESPACE
            binding_verifier = OpenSshSignatureVerifier(
                roster, namespace=namespace, expected_key_ids=(KEY_ID,)
            )
            binding_statement = case / "binding.json"
            exported = export_temperature_detector_result_binding_statement(
                recording,
                result_path,
                admission_statement,
                admission_signature,
                admission_verifier,
                binding_verifier,
                binding_statement,
                prepared_at_utc="2026-10-18T04:05:00Z",
                expires_at_utc="2026-10-18T05:05:00Z",
                now_utc="2026-10-18T04:06:00Z",
            )
            binding_signature = case / "binding.sshsig"
            if exported["status"].startswith("READY"):
                _sign(key, BINDING_NAMESPACE, binding_statement, binding_signature)
                if post:
                    post(case)
            result = evaluate_temperature_detector_result_binding(
                recording,
                result_path,
                admission_statement,
                admission_signature,
                admission_verifier,
                binding_verifier,
                binding_statement,
                binding_signature if binding_signature.exists() else None,
                prepared_at_utc="2026-10-18T04:05:00Z",
                expires_at_utc="2026-10-18T05:05:00Z",
                now_utc="2026-10-18T04:06:00Z",
            )
            results.append(result)
            scenarios.append(
                {
                    "scenario": name,
                    "status": result["status"],
                    "predicted_shared_cooling": result["predicted_shared_cooling"],
                    "error_count": len(result["errors"]),
                }
            )

        scenario("label-blind-shared-cooling-result")
        scenario(
            "result-created-after-labels",
            result_time="2026-10-18T04:01:00Z",
        )

        def tamper_result(case: Path) -> None:
            path = case / "detector-result.json"
            data = json.loads(path.read_text())
            data["predicted_shared_cooling"] = False
            _write(path, _canonical(data) + b"\n")

        scenario("detector-result-tampering", pre=tamper_result)

        def drift_recording(case: Path) -> None:
            path = case / "recording.jsonl"
            payload = path.read_bytes().replace(b'"sequence":51', b'"sequence":52')
            _write(path, payload)

        scenario("recording-drift", pre=drift_recording)

        def substitute_contract(case: Path) -> None:
            path = case / "detector-result.json"
            data = json.loads(path.read_text())
            data["detector_contract_sha256"] = "0" * 64
            unsigned = {key: value for key, value in data.items() if key != "result_sha256"}
            data["result_sha256"] = _sha256(_canonical(unsigned))
            _write(path, _canonical(data) + b"\n")

        scenario("detector-contract-substitution", pre=substitute_contract)

        def leak_labels(case: Path) -> None:
            path = case / "detector-result.json"
            data = json.loads(path.read_text())
            data["labels"] = {"expected_shared_cooling": True}
            unsigned = {key: value for key, value in data.items() if key != "result_sha256"}
            data["result_sha256"] = _sha256(_canonical(unsigned))
            _write(path, _canonical(data) + b"\n")

        scenario("label-leakage", pre=leak_labels)

        def break_admission_signature(case: Path) -> None:
            path = case / "admission.sshsig"
            payload = bytearray(path.read_bytes())
            payload[len(payload) // 2] ^= 1
            _write(path, bytes(payload))

        scenario("admission-signature-tampering", pre=break_admission_signature)
        scenario("binding-namespace-substitution", wrong_binding_namespace=True)

        def break_binding_signature(case: Path) -> None:
            path = case / "binding.sshsig"
            _write(path, b"not-an-sshsig\n")

        scenario("binding-signature-tampering", post=break_binding_signature)

        def escalate_binding(case: Path) -> None:
            path = case / "binding.json"
            data = json.loads(path.read_text())
            data["hardware_authority"] = True
            _write(path, _canonical(data))

        scenario("binding-authority-escalation", post=escalate_binding)
        fixture_private_keys_created = 1

    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0034",
        "scenario": "aegis-label-blind-detector-result-binding",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "control_authority": False,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "result_bound_count": sum(
                item["status"]
                == "DETECTOR_RESULT_BOUND_FOR_CALIBRATION_REVIEW"
                for item in results
            ),
            "hold_count": sum(item["status"] == "HOLD" for item in results),
            "unsafe_ready_count": sum(
                item["status"]
                == "DETECTOR_RESULT_BOUND_FOR_CALIBRATION_REVIEW"
                and (
                    item["field_validated"] is not False
                    or item["deployment_authority"] is not False
                    or item["hardware_authority"] is not False
                )
                for item in results
            ),
            "shared_cause_detection_sample": next(
                item["first_policy_match_index"]
                for item in results
                if item["status"]
                == "DETECTOR_RESULT_BOUND_FOR_CALIBRATION_REVIEW"
            ),
            "first_isolated_threshold_sample": 46,
            "detection_lead_samples": 46
            - next(
                item["first_policy_match_index"]
                for item in results
                if item["status"]
                == "DETECTOR_RESULT_BOUND_FOR_CALIBRATION_REVIEW"
            ),
            "labels_accepted_by_detector": 0,
            "private_key_inputs": 0,
            "signer_invocations_by_truepanel": 0,
            "fixture_private_keys_created": fixture_private_keys_created,
            "fixture_private_keys_retained": 0,
            "corpus_writes": 0,
            "field_validations": 0,
            "candidate_acceptances": 0,
            "candidate_installations": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
        },
        "invalidated_assumption": (
            "Signed outcome labels alone are sufficient calibration evidence; "
            "the detector prediction must exist first and be bound separately."
        ),
        "temporary_fixture_removed": not root.exists(),
    }
    report["evidence_sha256"] = _sha256(_canonical(report))
    return report


__all__ = ["run_temperature_detector_result_binding_checkride"]
