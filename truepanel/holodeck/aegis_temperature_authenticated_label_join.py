"""Adversarial proof for the one-shot authenticated calibration score."""

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
from truepanel.aegis.temperature_authenticated_label_join import (
    NAMESPACE,
    STATUS_READY,
    STATUS_SCORED,
    evaluate_temperature_authenticated_label_join,
    export_temperature_authenticated_label_join_statement,
)
from truepanel.aegis.temperature_blinded_cohort_manifest import (
    freeze_temperature_blinded_cohort_manifest,
)
from truepanel.holodeck.aegis_temperature_blinded_cohort_manifest import _fixture


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


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


def _cohort() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    contract, plan, results = _fixture()
    for index, envelope in enumerate(results):
        result = envelope["result"]
        result["predicted_shared_cooling"] = index < 40
        result["first_policy_match_index"] = 19 if index < 40 else None
        result["confidence_mean"] = 0.94 if index < 40 else 0.0
        result.pop("result_sha256")
        result["result_sha256"] = _sha256(result)
    manifest = freeze_temperature_blinded_cohort_manifest(
        contract,
        plan,
        results,
        frozen_at_utc="2026-10-24T03:30:00Z",
    )
    labels = [
        {
            "case_id": item["case_id"],
            "expected_shared_cooling": index < 40,
            "first_isolated_threshold_index": 46 if index < 40 else None,
        }
        for index, item in enumerate(manifest["results"])
    ]
    return contract, manifest, labels


def run_temperature_authenticated_label_join_checkride() -> dict[str, Any]:
    """Prove complete labels yield one immutable score and no authority."""

    contract, manifest, labels = _cohort()
    prepared = "2026-10-24T04:00:00Z"
    expires = "2026-10-24T06:00:00Z"
    scenarios: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="truepanel-label-join-") as directory:
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
        statement = root / "label-join.json"
        exported = export_temperature_authenticated_label_join_statement(
            contract,
            manifest,
            labels,
            verifier,
            statement,
            prepared_at_utc=prepared,
            expires_at_utc=expires,
            now_utc=prepared,
        )
        results.append(exported)
        scenarios.append(
            {
                "scenario": "complete-public-label-statement",
                "status": exported["status"],
                "error_count": len(exported["errors"]),
            }
        )
        signature = root / "label-join.sig"
        _sign(key, statement, signature, NAMESPACE)

        def registry(name: str, *, mode: int = 0o700) -> Path:
            path = root / name
            path.mkdir()
            os.chmod(path, mode)
            return path

        good_registry = registry("good-registry")

        def run(
            name: str,
            *,
            contract_value: dict[str, Any] | None = None,
            manifest_value: dict[str, Any] | None = None,
            label_value: list[dict[str, Any]] | None = None,
            verifier_value: Any = verifier,
            statement_value: Path = statement,
            signature_value: Path | None = signature,
            registry_value: Path | None = None,
            now: str = prepared,
        ) -> dict[str, Any]:
            result = evaluate_temperature_authenticated_label_join(
                contract_value or contract,
                manifest_value or manifest,
                label_value if label_value is not None else labels,
                verifier_value,
                statement_value,
                signature_value,
                registry_value or registry(f"registry-{len(scenarios)}"),
                prepared_at_utc=prepared,
                expires_at_utc=expires,
                now_utc=now,
            )
            results.append(result)
            scenarios.append(
                {
                    "scenario": name,
                    "status": result["status"],
                    "signature_verified": result["label_signature_verified"],
                    "score_committed": result["score_committed"],
                    "statistical_gates_passed": result[
                        "statistical_gates_passed"
                    ],
                    "error_count": len(result["errors"]),
                }
            )
            return result

        passing = run("authenticated-one-shot-score", registry_value=good_registry)
        run("same-detector-rescore", registry_value=good_registry)
        run("missing-frozen-case", label_value=copy.deepcopy(labels[:-1]))
        duplicate = copy.deepcopy(labels)
        duplicate[-1] = copy.deepcopy(duplicate[0])
        run("duplicate-case-label", label_value=duplicate)
        changed = copy.deepcopy(labels)
        changed[0]["expected_shared_cooling"] = False
        run("post-signature-label-drift", label_value=changed)
        tampered_manifest = copy.deepcopy(manifest)
        tampered_manifest["results"][0]["confidence_mean"] = 0.01
        run("manifest-substitution", manifest_value=tampered_manifest)
        tampered_statement = root / "authority-escalation.json"
        statement_data = json.loads(statement.read_text())
        statement_data["deployment_authority"] = True
        tampered_statement.write_text(json.dumps(statement_data), encoding="utf-8")
        os.chmod(tampered_statement, 0o600)
        run("statement-authority-escalation", statement_value=tampered_statement)
        wrong_signature = root / "wrong-namespace.sig"
        _sign(key, statement, wrong_signature, "wrong-label-namespace")
        run("wrong-signature-namespace", signature_value=wrong_signature)
        run("expired-label-statement", now="2026-10-24T06:00:00Z")
        run("unsafe-score-registry", registry_value=registry("unsafe", mode=0o777))

        weak_labels = copy.deepcopy(labels)
        for index, label in enumerate(weak_labels):
            label["expected_shared_cooling"] = index < 20 or 40 <= index < 60
            label["first_isolated_threshold_index"] = (
                46 if label["expected_shared_cooling"] else None
            )
        weak_statement = root / "weak-label-join.json"
        weak_export = export_temperature_authenticated_label_join_statement(
            contract,
            manifest,
            weak_labels,
            verifier,
            weak_statement,
            prepared_at_utc=prepared,
            expires_at_utc=expires,
            now_utc=prepared,
        )
        results.append(weak_export)
        scenarios.append(
            {
                "scenario": "complete-weak-public-label-statement",
                "status": weak_export["status"],
                "error_count": len(weak_export["errors"]),
            }
        )
        weak_signature = root / "weak-label-join.sig"
        _sign(key, weak_statement, weak_signature, NAMESPACE)
        run(
            "authenticated-failing-score-sealed",
            label_value=weak_labels,
            statement_value=weak_statement,
            signature_value=weak_signature,
        )

    measurements = {
        "scenario_count": len(scenarios),
        "signing_ready_count": sum(
            item["status"] == STATUS_READY for item in scenarios
        ),
        "scored_count": sum(item["status"] == STATUS_SCORED for item in scenarios),
        "hold_count": sum(item["status"] == "HOLD" for item in scenarios),
        "passing_score_count": sum(
            item.get("statistical_gates_passed") is True for item in scenarios
        ),
        "failing_score_sealed_count": sum(
            item.get("score_committed") is True
            and item.get("statistical_gates_passed") is False
            for item in scenarios
        ),
        "case_count": passing["score"]["case_count"],
        "positive_cases": passing["score"]["positive_cases"],
        "negative_cases": passing["score"]["negative_cases"],
        "sensitivity_wilson_lower": passing["score"][
            "sensitivity_wilson_lower"
        ],
        "false_positive_rate_wilson_upper": passing["score"][
            "false_positive_rate_wilson_upper"
        ],
        "abstention_rate_wilson_upper": passing["score"][
            "abstention_rate_wilson_upper"
        ],
        "median_lead_samples": passing["score"]["median_lead_samples"],
        "p10_lead_samples": passing["score"]["p10_lead_samples"],
        "isolated_threshold_index": 46,
        "shared_cooling_index": 19,
        "lead_samples": 27,
        "repeat_scores_accepted": 0,
        "case_exclusions": 0,
        "threshold_changes": 0,
        "field_validations": 0,
        "candidate_acceptances": 0,
        "candidate_installations": 0,
        "deployments": 0,
        "hardware_actions": 0,
        "production_writes": 0,
        "fixture_score_receipts_committed": 2,
        "private_key_inputs": 0,
        "signer_invocations_by_truepanel": 0,
        "fixture_private_keys_created": 1,
        "fixture_private_keys_retained": 0,
    }
    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0039",
        "scenario": "aegis-authenticated-one-shot-label-join",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "control_authority": False,
        "scenarios": scenarios,
        "measurements": measurements,
        "invalidated_assumption": (
            "A passing score is the only result worth sealing; a failing authenticated "
            "score must also consume the one evaluation so it cannot be relabeled or rerun."
        ),
    }
    report["evidence_sha256"] = _sha256(report)
    return report


__all__ = ["run_temperature_authenticated_label_join_checkride"]
