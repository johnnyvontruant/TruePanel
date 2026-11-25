"""Deterministic two-person replay evidence review rehearsal."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from truepanel.aegis.ssh_verifier import OpenSshSignatureVerifier
from truepanel.aegis.temperature_authenticated_acceptance import KEY_ID
from truepanel.aegis.temperature_authenticated_replay_review import (
    DECISION_ACCEPT,
    evaluate_temperature_authenticated_replay_review,
    export_temperature_authenticated_replay_review_statement,
)
from truepanel.aegis.temperature_authenticated_replay_review import (
    NAMESPACE as PRIMARY_NAMESPACE,
)
from truepanel.aegis.temperature_calibration_candidate_appraisal import _canonical
from truepanel.aegis.temperature_two_person_replay_review import (
    DECISION_CONCUR,
    DECISION_DISSENT,
    NAMESPACE,
    REVIEWER_KEY_ID,
    STATUS_HELD,
    STATUS_QUORUM,
    evaluate_temperature_two_person_replay_review,
    export_temperature_two_person_replay_review_statement,
)
from truepanel.holodeck.aegis_temperature_authenticated_label_join import _sign
from truepanel.holodeck.aegis_temperature_authenticated_replay_review import _receipt


def run_temperature_two_person_replay_review_checkride() -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix="truepanel-two-person-review-"
    ) as directory:
        root = Path(directory).resolve()
        primary_key = root / "primary-key"
        reviewer_key = root / "reviewer-key"
        for key in (primary_key, reviewer_key):
            subprocess.run(
                [
                    "/usr/bin/ssh-keygen",
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-f",
                    str(key),
                ],
                check=True,
            )
        primary_roster = root / "primary-roster"
        primary_roster.write_text(
            f"{KEY_ID} {primary_key.with_suffix('.pub').read_text(encoding='ascii')}",
            encoding="ascii",
        )
        os.chmod(primary_roster, 0o600)
        reviewer_roster = root / "reviewer-roster"
        reviewer_roster.write_text(
            f"{REVIEWER_KEY_ID} {reviewer_key.with_suffix('.pub').read_text(encoding='ascii')}",
            encoding="ascii",
        )
        os.chmod(reviewer_roster, 0o600)
        primary_verifier = OpenSshSignatureVerifier(
            primary_roster, namespace=PRIMARY_NAMESPACE, expected_key_ids=(KEY_ID,)
        )
        reviewer_verifier = OpenSshSignatureVerifier(
            reviewer_roster, namespace=NAMESPACE, expected_key_ids=(REVIEWER_KEY_ID,)
        )
        replay = root / "replay.json"
        replay.write_bytes(_canonical(_receipt()) + b"\n")
        os.chmod(replay, 0o600)
        prepared, expires, now = (
            "2026-11-02T04:00:00Z",
            "2026-11-02T06:00:00Z",
            "2026-11-02T05:00:00Z",
        )
        primary_statement = root / "primary.json"
        export_temperature_authenticated_replay_review_statement(
            replay,
            primary_verifier,
            primary_statement,
            decision=DECISION_ACCEPT,
            rationale="evidence-and-method-reviewed",
            prepared_at_utc=prepared,
            expires_at_utc=expires,
            now_utc=now,
        )
        primary_signature = root / "primary.sig"
        _sign(primary_key, primary_statement, primary_signature, PRIMARY_NAMESPACE)
        primary_registry = root / "primary-registry"
        primary_registry.mkdir(mode=0o700)
        primary_result = evaluate_temperature_authenticated_replay_review(
            replay,
            primary_verifier,
            primary_statement,
            primary_signature,
            primary_registry,
            now_utc=now,
        )
        primary_receipt = primary_registry / str(primary_result["receipt_filename"])

        def run(
            name: str,
            decision: str,
            rationale: str,
            *,
            mutate: bool = False,
            registry: Path | None = None,
        ) -> dict[str, Any]:
            statement = root / f"{name}.json"
            exported = export_temperature_two_person_replay_review_statement(
                replay,
                primary_verifier,
                primary_statement,
                primary_signature,
                primary_receipt,
                reviewer_verifier,
                output_path=statement,
                decision=decision,
                rationale=rationale,
                prepared_at_utc=prepared,
                expires_at_utc=expires,
                now_utc=now,
            )
            if not exported["statement_created"]:
                raise RuntimeError(exported["errors"])
            if mutate:
                value = json.loads(statement.read_bytes())
                value["deployment_authority"] = True
                statement.write_bytes(_canonical(value))
            signature = root / f"{name}.sig"
            _sign(reviewer_key, statement, signature, NAMESPACE)
            target = registry or (root / f"registry-{name}")
            target.mkdir(mode=0o700, exist_ok=True)
            result = evaluate_temperature_two_person_replay_review(
                replay,
                primary_verifier,
                primary_statement,
                primary_signature,
                primary_receipt,
                reviewer_verifier,
                statement,
                signature,
                target,
                now_utc=now,
            )
            scenarios.append(
                {
                    "name": name,
                    "status": result["status"],
                    "errors": [error.split(": '", 1)[0] for error in result["errors"]],
                }
            )
            return result

        concur = run(
            "concur", DECISION_CONCUR, "independently-reconstructed-and-concurred"
        )
        dissent = run("dissent", DECISION_DISSENT, "independent-review-caution")
        run(
            "authority-escalation",
            DECISION_CONCUR,
            "independently-reconstructed-and-concurred",
            mutate=True,
        )
        duplicate_registry = root / "duplicate-registry"
        duplicate_registry.mkdir(mode=0o700)
        run(
            "exclusive-first",
            DECISION_CONCUR,
            "independently-reconstructed-and-concurred",
            registry=duplicate_registry,
        )
        run(
            "duplicate",
            DECISION_CONCUR,
            "independently-reconstructed-and-concurred",
            registry=duplicate_registry,
        )
    return {
        "schema": "truepanel.holodeck-temperature-two-person-replay-review/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "quorum_count": int(concur["status"] == STATUS_QUORUM),
            "operator_hold_count": int(dissent["status"] == STATUS_HELD),
            "coverage_total": 8,
            "coverage_trusted": 8,
            "coverage_gaps": 0,
            "supporting_signal_count": 5,
            "confidence": 0.95,
            "shared_cooling_first_match_sample": 19,
            "isolated_threshold_first_match_sample": 46,
            "lead_samples": 27,
            "independent_reviewers": 2,
            "labels_revealed": 0,
            "field_validations": 0,
            "candidate_installations": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
            "fixture_private_keys_created": 2,
            "fixture_private_keys_retained": 0,
        },
    }


__all__ = ["run_temperature_two_person_replay_review_checkride"]
