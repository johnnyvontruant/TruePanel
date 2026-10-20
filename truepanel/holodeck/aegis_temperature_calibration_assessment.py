"""Adversarial proof for read-only authenticated corpus characterization."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from truepanel.aegis.ssh_verifier import OpenSshSignatureVerifier
from truepanel.aegis.temperature_authenticated_acceptance import KEY_ID
from truepanel.aegis.temperature_calibration_admission import NAMESPACE
from truepanel.aegis.temperature_calibration_assessment import (
    assess_temperature_calibration_corpus,
)
from truepanel.aegis.temperature_calibration_corpus import (
    CORPUS_SCHEMA,
    _canonical,
    _write_complete,
)
from truepanel.aegis.temperature_calibration_corpus import (
    SCHEMA as IMPORT_SCHEMA,
)
from truepanel.holodeck.aegis_temperature_calibration_admission import _sign


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _metadata(corpus_id: str) -> bytes:
    return _canonical(
        {
            "schema": CORPUS_SCHEMA,
            "corpus_id": corpus_id,
            "storage": "append-only-case-directories",
            "field_validated": False,
            "production_validated": False,
            "deployment_authority": False,
            "hardware_authority": False,
        }
    ) + b"\n"


def _refresh_receipt(case: Path) -> None:
    path = case / "import-receipt.json"
    receipt = json.loads(path.read_text())
    receipt.pop("receipt_sha256", None)
    receipt["receipt_sha256"] = _sha256(_canonical(receipt))
    path.write_bytes(_canonical(receipt) + b"\n")
    os.chmod(path, 0o600)


def _fixture_corpus(root: Path, key: Path, corpus_id: str) -> Path:
    corpus = root / "corpus"
    cases = corpus / "cases"
    cases.mkdir(parents=True, mode=0o700)
    os.chmod(corpus, 0o700)
    _write_complete(corpus / "corpus.json", _metadata(corpus_id))
    _write_complete(corpus / ".import.lock", b"")
    definitions = (
        ("cooling-001", True, "qnap-six-bay", "storage-heavy", 3),
        ("cooling-002", True, "qnap-eight-bay", "mixed-io", 4),
        ("normal-001", False, "qnap-six-bay", "mixed-io", None),
        ("normal-002", False, "qnap-eight-bay", "storage-heavy", None),
    )
    for index, (case_id, expected, profile, workload, threshold) in enumerate(
        definitions
    ):
        case = cases / case_id
        case.mkdir(mode=0o700)
        frames = [
            {"schema_version": 1, "sequence": item, "captured_at": float(item),
             "privacy": "sanitized", "storage": {"temperatures": []}}
            for item in range(4)
        ]
        frames[-1]["fixture_variant"] = index
        recording = b"".join(_canonical(frame) + b"\n" for frame in frames)
        labels = {
            "corpus_id": corpus_id,
            "case_id": case_id,
            "challenge": "fan-degradation-thermal-drift" if expected else "stable-cooling",
            "system_profile": profile,
            "workload_class": workload,
            "expected_shared_cooling": expected,
            "first_isolated_threshold_index": threshold,
        }
        statement_data = {
            "schema": "truepanel.aegis-temperature-calibration-admission-statement/v1",
            "namespace": NAMESPACE,
            "scope": "temperature-calibration-corpus-import-only",
            "key_id": KEY_ID,
            "operator_key_fingerprint": "fixture-bound-by-openssh",
            "prepared_at_utc": "2026-10-18T04:00:00Z",
            "expires_at_utc": "2026-10-18T05:00:00Z",
            "recording_sha256": _sha256(recording),
            "recording_bytes": len(recording),
            "frame_count": 4,
            "labels": labels,
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
        statement = _canonical(statement_data)
        _write_complete(case / "recording.jsonl", recording)
        _write_complete(case / "admission-statement.json", statement)
        signature_path = case / "admission-signature.sshsig"
        _sign(key, case / "admission-statement.json", signature_path, NAMESPACE)
        signature = signature_path.read_bytes()
        receipt = {
            "schema": IMPORT_SCHEMA,
            "corpus_id": corpus_id,
            "case_id": case_id,
            "recording_sha256": _sha256(recording),
            "recording_bytes": len(recording),
            "frame_count": 4,
            "admission_record_sha256": f"fixture-{index}",
            "admission_statement_sha256": _sha256(statement),
            "admission_signature_sha256": _sha256(signature),
            "admission_signature_bytes": len(signature),
            "labels": labels,
            "imported_for_offline_analysis": True,
            "field_validated": False,
            "production_validated": False,
            "candidate_accepted": False,
            "candidate_installed": False,
            "runtime_authority": False,
            "deployment_authority": False,
            "hardware_authority": False,
            "automatic_promotion": False,
        }
        receipt["receipt_sha256"] = _sha256(_canonical(receipt))
        _write_complete(case / "import-receipt.json", _canonical(receipt) + b"\n")
    return corpus


def run_temperature_calibration_assessment_checkride() -> dict[str, Any]:
    """Prove sufficiency remains distinct from validation or promotion."""

    corpus_id = "aegis-field-corpus-v1"
    scenarios: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="truepanel-calibration-assessment-") as directory:
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
        baseline = _fixture_corpus(root / "baseline", key, corpus_id)

        def run(name: str, mutate: Any | None = None, custom_verifier: Any = None) -> None:
            destination = root / name
            shutil.copytree(baseline, destination)
            if mutate:
                mutate(destination)
            result = assess_temperature_calibration_corpus(
                destination, corpus_id, custom_verifier or verifier
            )
            results.append(result)
            scenarios.append(
                {"scenario": name, "status": result["status"],
                 "case_count": result["case_count"], "errors": result["errors"]}
            )

        run("balanced-authenticated-corpus")
        run("insufficient-case-floor", lambda path: shutil.rmtree(path / "cases" / "normal-002"))

        def all_positive(path: Path) -> None:
            for case in (path / "cases").iterdir():
                statement_path = case / "admission-statement.json"
                statement = json.loads(statement_path.read_text())
                statement["labels"]["expected_shared_cooling"] = True
                statement_path.write_bytes(_canonical(statement))
                _sign(key, statement_path, case / "admission-signature.sshsig", NAMESPACE)
                receipt = json.loads((case / "import-receipt.json").read_text())
                receipt["labels"] = statement["labels"]
                receipt["admission_statement_sha256"] = _sha256(statement_path.read_bytes())
                signature = (case / "admission-signature.sshsig").read_bytes()
                receipt["admission_signature_sha256"] = _sha256(signature)
                receipt["admission_signature_bytes"] = len(signature)
                (case / "import-receipt.json").write_bytes(_canonical(receipt) + b"\n")
                _refresh_receipt(case)
        run("outcome-imbalance", all_positive)

        def one_profile(path: Path) -> None:
            for case in (path / "cases").iterdir():
                statement_path = case / "admission-statement.json"
                statement = json.loads(statement_path.read_text())
                statement["labels"]["system_profile"] = "qnap-six-bay"
                statement_path.write_bytes(_canonical(statement))
                _sign(key, statement_path, case / "admission-signature.sshsig", NAMESPACE)
                receipt = json.loads((case / "import-receipt.json").read_text())
                receipt["labels"] = statement["labels"]
                receipt["admission_statement_sha256"] = _sha256(statement_path.read_bytes())
                signature = (case / "admission-signature.sshsig").read_bytes()
                receipt["admission_signature_sha256"] = _sha256(signature)
                receipt["admission_signature_bytes"] = len(signature)
                (case / "import-receipt.json").write_bytes(_canonical(receipt) + b"\n")
                _refresh_receipt(case)
        run("profile-collapse", one_profile)

        def bad_signature(path: Path) -> None:
            target = path / "cases" / "cooling-001" / "admission-signature.sshsig"
            lines = target.read_text(encoding="ascii").splitlines()
            lines[1] = ("V" if lines[1][0] != "V" else "U") + lines[1][1:]
            target.write_text("\n".join(lines) + "\n", encoding="ascii")
            receipt = path / "cases" / "cooling-001" / "import-receipt.json"
            data = json.loads(receipt.read_text())
            payload = target.read_bytes()
            data["admission_signature_sha256"] = _sha256(payload)
            data["admission_signature_bytes"] = len(payload)
            receipt.write_bytes(_canonical(data) + b"\n")
            _refresh_receipt(receipt.parent)
        run("signature-tampering", bad_signature)

        def lineage_drift(path: Path) -> None:
            receipt = path / "cases" / "cooling-001" / "import-receipt.json"
            data = json.loads(receipt.read_text())
            data["labels"]["workload_class"] = "substituted"
            receipt.write_bytes(_canonical(data) + b"\n")
            _refresh_receipt(receipt.parent)
        run("lineage-substitution", lineage_drift)

        def authority_escalation(path: Path) -> None:
            case = path / "cases" / "cooling-001"
            statement_path = case / "admission-statement.json"
            statement = json.loads(statement_path.read_text())
            statement["deployment_authority"] = True
            statement_path.write_bytes(_canonical(statement))
            _sign(key, statement_path, case / "admission-signature.sshsig", NAMESPACE)
            receipt = json.loads((case / "import-receipt.json").read_text())
            receipt["admission_statement_sha256"] = _sha256(statement_path.read_bytes())
            signature = (case / "admission-signature.sshsig").read_bytes()
            receipt["admission_signature_sha256"] = _sha256(signature)
            receipt["admission_signature_bytes"] = len(signature)
            (case / "import-receipt.json").write_bytes(_canonical(receipt) + b"\n")
            _refresh_receipt(case)
        run("signed-authority-escalation", authority_escalation)

        def recording_drift(path: Path) -> None:
            recording = path / "cases" / "normal-001" / "recording.jsonl"
            recording.write_bytes(recording.read_bytes() + b"{}\n")
        run("recording-drift", recording_drift)

        wrong = OpenSshSignatureVerifier(
            roster, namespace="wrong-namespace", expected_key_ids=(KEY_ID,)
        )
        run("verifier-policy-drift", custom_verifier=wrong)

    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0033",
        "scenario": "aegis-read-only-authenticated-calibration-corpus-assessment",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "control_authority": False,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(results),
            "review_ready_count": sum(
                item["status"] == "CALIBRATION_CORPUS_CHARACTERIZED_FOR_INDEPENDENT_REVIEW"
                for item in results
            ),
            "hold_count": sum(item["status"] == "HOLD" for item in results),
            "authenticated_cases_in_ready_corpus": results[0]["case_count"],
            "positive_cases": results[0]["positive_cases"],
            "negative_cases": results[0]["negative_cases"],
            "system_profiles": len(results[0]["system_profiles"]),
            "workload_classes": len(results[0]["workload_classes"]),
            "corpus_writes": 0,
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
            "before": "a corpus receipt could be inspected without preserving or replaying its detached admission signature",
            "after": "every immutable case preserves and re-verifies the exact signed admission before diversity gates are computed",
            "result": "small imbalanced non-diverse or tampered corpora remain HOLD and no assessment becomes validation",
        },
        "temporary_fixture_removed": not root.exists(),
    }
    report["evidence_sha256"] = _sha256(_canonical(report))
    return report


__all__ = ["run_temperature_calibration_assessment_checkride"]
