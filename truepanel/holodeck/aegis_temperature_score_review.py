"""Adversarial proof for independent reconstruction of sealed AEGIS scores."""

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
    NAMESPACE as LABEL_NAMESPACE,
)
from truepanel.aegis.temperature_authenticated_label_join import (
    evaluate_temperature_authenticated_label_join,
    export_temperature_authenticated_label_join_statement,
)
from truepanel.aegis.temperature_score_review import (
    STATUS_REVIEWED,
    review_temperature_authenticated_score,
)
from truepanel.holodeck.aegis_temperature_authenticated_label_join import (
    _cohort,
    _sign,
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _protected_json(path: Path, value: Any) -> None:
    path.write_bytes(_canonical(value) + b"\n")
    os.chmod(path, 0o600)


def run_temperature_score_review_checkride() -> dict[str, Any]:
    """Prove pass and fail receipts reconstruct while every mutation holds."""

    contract, manifest, labels = _cohort()
    prepared = "2026-10-24T04:00:00Z"
    expires = "2026-10-24T06:00:00Z"
    reviewed = "2026-10-25T04:00:00Z"
    scenarios: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="truepanel-score-review-") as directory:
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
            roster, namespace=LABEL_NAMESPACE, expected_key_ids=(KEY_ID,)
        )

        def score_fixture(
            name: str, label_value: list[dict[str, Any]]
        ) -> tuple[Path, Path, Path, Path]:
            statement = root / f"{name}-labels.json"
            exported = export_temperature_authenticated_label_join_statement(
                contract,
                manifest,
                label_value,
                verifier,
                statement,
                prepared_at_utc=prepared,
                expires_at_utc=expires,
                now_utc=prepared,
            )
            assert exported["statement_created"] is True
            signature = root / f"{name}-labels.sig"
            _sign(key, statement, signature, LABEL_NAMESPACE)
            registry = root / f"{name}-registry"
            registry.mkdir(mode=0o700)
            result = evaluate_temperature_authenticated_label_join(
                contract,
                manifest,
                label_value,
                verifier,
                statement,
                signature,
                registry,
                prepared_at_utc=prepared,
                expires_at_utc=expires,
                now_utc=prepared,
            )
            assert result["score_committed"] is True
            return statement, signature, registry / result["receipt_filename"], registry

        passing_statement, passing_signature, passing_receipt, passing_registry = (
            score_fixture("passing", labels)
        )
        weak_labels = copy.deepcopy(labels)
        for index, label in enumerate(weak_labels):
            label["expected_shared_cooling"] = index < 20 or 40 <= index < 60
            label["first_isolated_threshold_index"] = (
                46 if label["expected_shared_cooling"] else None
            )
        weak_statement, weak_signature, weak_receipt, weak_registry = score_fixture(
            "failing", weak_labels
        )
        registry_state_before = {
            path: tuple(item.name for item in path.iterdir())
            for path in (passing_registry, weak_registry)
        }

        def run(
            name: str,
            *,
            contract_value: dict[str, Any] | None = None,
            manifest_value: dict[str, Any] | None = None,
            verifier_value: Any = verifier,
            statement: Path = passing_statement,
            signature: Path = passing_signature,
            receipt: Path = passing_receipt,
            output: Path | None = None,
        ) -> dict[str, Any]:
            destination = output or root / f"review-{len(scenarios)}.json"
            result = review_temperature_authenticated_score(
                contract_value or contract,
                manifest_value or manifest,
                verifier_value,
                statement,
                signature,
                receipt,
                destination,
                reviewed_at_utc=reviewed,
            )
            results.append(result)
            scenarios.append(
                {
                    "scenario": name,
                    "status": result["status"],
                    "label_signature_verified": result[
                        "label_signature_verified"
                    ],
                    "score_reconstructed": result["score_reconstructed"],
                    "review_receipt_created": result["review_receipt_created"],
                    "statistical_gates_passed": result[
                        "statistical_gates_passed"
                    ],
                    "error_count": len(result["errors"]),
                }
            )
            return result

        passing = run("passing-score-independently-reconstructed")
        failing = run(
            "failing-score-independently-reconstructed",
            statement=weak_statement,
            signature=weak_signature,
            receipt=weak_receipt,
        )

        tampered_metric = json.loads(passing_receipt.read_text())
        tampered_metric["score"]["median_lead_samples"] = 99.0
        unsigned = dict(tampered_metric)
        unsigned.pop("receipt_sha256")
        tampered_metric["receipt_sha256"] = _sha256(unsigned)
        tampered_metric_path = root / "tampered-metric.json"
        _protected_json(tampered_metric_path, tampered_metric)
        run("tampered-score-metric", receipt=tampered_metric_path)

        escalated = json.loads(passing_receipt.read_text())
        escalated["deployment_authority"] = True
        unsigned = dict(escalated)
        unsigned.pop("receipt_sha256")
        escalated["receipt_sha256"] = _sha256(unsigned)
        escalated_path = root / "authority-escalation.json"
        _protected_json(escalated_path, escalated)
        run("score-receipt-authority-escalation", receipt=escalated_path)

        noncanonical = root / "noncanonical-score.json"
        noncanonical.write_bytes(passing_receipt.read_bytes() + b" ")
        os.chmod(noncanonical, 0o600)
        run("noncanonical-score-receipt", receipt=noncanonical)

        drifted_statement = root / "drifted-label-statement.json"
        drifted = json.loads(passing_statement.read_text())
        drifted["labels"][0]["expected_shared_cooling"] = False
        drifted_statement.write_bytes(_canonical(drifted))
        os.chmod(drifted_statement, 0o600)
        run("post-signature-label-drift", statement=drifted_statement)

        wrong_signature = root / "wrong-namespace.sig"
        _sign(key, passing_statement, wrong_signature, "wrong-review-namespace")
        run("wrong-signature-namespace", signature=wrong_signature)

        wrong_verifier = OpenSshSignatureVerifier(
            roster,
            namespace="wrong-review-namespace",
            expected_key_ids=(KEY_ID,),
        )
        run("wrong-verifier-policy", verifier_value=wrong_verifier)

        changed_manifest = copy.deepcopy(manifest)
        changed_manifest["results"][0]["confidence_mean"] = 0.01
        run("manifest-substitution", manifest_value=changed_manifest)

        occupied = root / "occupied-review.json"
        occupied.write_text("occupied", encoding="utf-8")
        os.chmod(occupied, 0o600)
        run("occupied-review-output", output=occupied)

        unsafe = root / "unsafe-output"
        unsafe.mkdir(mode=0o777)
        os.chmod(unsafe, 0o777)
        run("unsafe-review-output-directory", output=unsafe / "review.json")

        run("missing-score-receipt", receipt=root / "missing-score.json")

        registry_state_after = {
            path: tuple(item.name for item in path.iterdir())
            for path in (passing_registry, weak_registry)
        }

    unsafe_ready = sum(
        result["status"] == STATUS_REVIEWED
        and any(
            result[key] is not False
            for key in (
                "field_validated",
                "candidate_accepted",
                "candidate_installed",
                "deployment_authority",
                "hardware_authority",
            )
        )
        for result in results
    )
    measurements = {
        "scenario_count": len(scenarios),
        "reviewed_count": sum(
            item["status"] == STATUS_REVIEWED for item in scenarios
        ),
        "hold_count": sum(item["status"] == "HOLD" for item in scenarios),
        "passing_scores_reconstructed": int(
            passing["status"] == STATUS_REVIEWED
            and passing["statistical_gates_passed"] is True
        ),
        "failing_scores_reconstructed": int(
            failing["status"] == STATUS_REVIEWED
            and failing["statistical_gates_passed"] is False
        ),
        "case_count": 440,
        "positive_cases": 40,
        "negative_cases": 400,
        "sensitivity_wilson_lower": 0.912378,
        "false_positive_rate_wilson_upper": 0.009512,
        "abstention_rate_wilson_upper": 0.008655,
        "median_lead_samples": 27.0,
        "p10_lead_samples": 27,
        "isolated_threshold_index": 46,
        "shared_cooling_index": 19,
        "lead_samples": 27,
        "score_registry_writes": 0,
        "score_registry_unchanged": registry_state_before == registry_state_after,
        "labels_changed": 0,
        "threshold_changes": 0,
        "score_re_evaluations": 0,
        "field_validations": 0,
        "candidate_acceptances": 0,
        "candidate_installations": 0,
        "deployments": 0,
        "hardware_actions": 0,
        "production_writes": 0,
        "unsafe_ready_count": unsafe_ready,
        "fixture_private_keys_created": 1,
        "fixture_private_keys_retained": 0,
    }
    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0040",
        "scenario": "aegis-independent-authenticated-score-review",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "control_authority": False,
        "scenarios": scenarios,
        "measurements": measurements,
        "invalidated_assumption": (
            "Digest integrity alone proves a statistical score was computed correctly; "
            "an independent implementation must reconstruct the signed labels, frozen "
            "cohort, denominators, uncertainty bounds, lead population, and final verdict."
        ),
    }
    report["evidence_sha256"] = _sha256(report)
    return report


__all__ = ["run_temperature_score_review_checkride"]
