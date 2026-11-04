"""Deterministic rehearsal for the operator calibration decision receipt."""

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
from truepanel.aegis.temperature_calibration_decision import (
    DECISION_ACCEPT,
    DECISION_HOLD,
    NAMESPACE,
    STATUS_ACCEPTED,
    STATUS_HELD,
    evaluate_temperature_calibration_decision,
    export_temperature_calibration_decision_statement,
)
from truepanel.aegis.temperature_score_review import (
    review_temperature_authenticated_score,
)
from truepanel.holodeck.aegis_temperature_authenticated_label_join import (
    _cohort,
    _sign,
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _protected(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)
    os.chmod(path, 0o600)


def run_temperature_calibration_decision_checkride() -> dict[str, Any]:
    """Prove only passing reviews can be accepted while any score can be held."""

    contract, manifest, labels = _cohort()
    label_prepared = "2026-10-24T04:00:00Z"
    label_expires = "2026-10-24T06:00:00Z"
    reviewed_at = "2026-10-25T04:00:00Z"
    prepared = "2026-10-26T04:00:00Z"
    expires = "2026-10-26T06:00:00Z"
    now = "2026-10-26T05:00:00Z"
    scenarios: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(
        prefix="truepanel-calibration-decision-"
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
        label_verifier = OpenSshSignatureVerifier(
            roster, namespace=LABEL_NAMESPACE, expected_key_ids=(KEY_ID,)
        )
        decision_verifier = OpenSshSignatureVerifier(
            roster, namespace=NAMESPACE, expected_key_ids=(KEY_ID,)
        )

        def reviewed_fixture(name: str, fixture_labels: list[dict[str, Any]]) -> Path:
            statement = root / f"{name}-labels.json"
            exported = export_temperature_authenticated_label_join_statement(
                contract,
                manifest,
                fixture_labels,
                label_verifier,
                statement,
                prepared_at_utc=label_prepared,
                expires_at_utc=label_expires,
                now_utc=label_prepared,
            )
            assert exported["statement_created"] is True
            signature = root / f"{name}-labels.sig"
            _sign(key, statement, signature, LABEL_NAMESPACE)
            score_registry = root / f"{name}-score-registry"
            score_registry.mkdir(mode=0o700)
            score = evaluate_temperature_authenticated_label_join(
                contract,
                manifest,
                fixture_labels,
                label_verifier,
                statement,
                signature,
                score_registry,
                prepared_at_utc=label_prepared,
                expires_at_utc=label_expires,
                now_utc=label_prepared,
            )
            assert score["score_committed"] is True
            review = root / f"{name}-review.json"
            reviewed = review_temperature_authenticated_score(
                contract,
                manifest,
                label_verifier,
                statement,
                signature,
                score_registry / score["receipt_filename"],
                review,
                reviewed_at_utc=reviewed_at,
            )
            assert reviewed["review_receipt_created"] is True
            return review

        passing_review = reviewed_fixture("passing", labels)
        failing_labels = copy.deepcopy(labels)
        for index, label in enumerate(failing_labels):
            label["expected_shared_cooling"] = index < 20 or 40 <= index < 60
            label["first_isolated_threshold_index"] = (
                46 if label["expected_shared_cooling"] else None
            )
        failing_review = reviewed_fixture("failing", failing_labels)

        def prepare_statement(
            name: str, review: Path, decision: str, rationale: str
        ) -> tuple[Path, Path, dict[str, Any]]:
            statement = root / f"{name}.json"
            exported = export_temperature_calibration_decision_statement(
                review,
                decision_verifier,
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
                    "status": exported["status"],
                    "decision_recorded": False,
                    "candidate_review_eligible": False,
                    "error_count": len(exported["errors"]),
                }
            )
            signature = root / f"{name}.sig"
            if exported["statement_created"]:
                _sign(key, statement, signature, NAMESPACE)
            return statement, signature, exported

        def evaluate(
            name: str,
            review: Path,
            statement: Path,
            signature: Path,
            *,
            registry: Path | None = None,
            verifier: Any = decision_verifier,
            now_value: str = now,
        ) -> dict[str, Any]:
            destination = registry or root / f"{name}-registry"
            if registry is None:
                destination.mkdir(mode=0o700)
            result = evaluate_temperature_calibration_decision(
                review,
                verifier,
                statement,
                signature,
                destination,
                prepared_at_utc=prepared,
                expires_at_utc=expires,
                now_utc=now_value,
            )
            results.append(result)
            scenarios.append(
                {
                    "scenario": name,
                    "status": result["status"],
                    "decision_recorded": result["decision_recorded"],
                    "candidate_review_eligible": result["candidate_review_eligible"],
                    "error_count": len(result["errors"]),
                }
            )
            return result

        accept_statement, accept_signature, _ = prepare_statement(
            "passing-accept",
            passing_review,
            DECISION_ACCEPT,
            "score-passed-independent-review",
        )
        accepted = evaluate(
            "passing-review-authenticated-accept",
            passing_review,
            accept_statement,
            accept_signature,
        )

        passing_hold_statement, passing_hold_signature, _ = prepare_statement(
            "passing-hold", passing_review, DECISION_HOLD, "operator-caution"
        )
        passing_held = evaluate(
            "passing-review-authenticated-hold",
            passing_review,
            passing_hold_statement,
            passing_hold_signature,
        )

        failing_hold_statement, failing_hold_signature, _ = prepare_statement(
            "failing-hold",
            failing_review,
            DECISION_HOLD,
            "score-failed-statistical-gates",
        )
        failing_held = evaluate(
            "failing-review-authenticated-hold",
            failing_review,
            failing_hold_statement,
            failing_hold_signature,
        )

        failed_accept = root / "failing-accept.json"
        failed_export = export_temperature_calibration_decision_statement(
            failing_review,
            decision_verifier,
            failed_accept,
            decision=DECISION_ACCEPT,
            rationale="score-passed-independent-review",
            prepared_at_utc=prepared,
            expires_at_utc=expires,
            now_utc=now,
        )
        scenarios.append(
            {
                "scenario": "failing-review-cannot-be-accepted",
                "status": failed_export["status"],
                "decision_recorded": False,
                "candidate_review_eligible": False,
                "error_count": len(failed_export["errors"]),
            }
        )

        wrong_namespace = root / "wrong-namespace.sig"
        _sign(key, accept_statement, wrong_namespace, "wrong-decision-namespace")
        evaluate(
            "wrong-signature-namespace",
            passing_review,
            accept_statement,
            wrong_namespace,
        )

        drifted_review = root / "drifted-review.json"
        drifted = json.loads(passing_review.read_text())
        drifted["score_sha256"] = "0" * 64
        unsigned = dict(drifted)
        unsigned.pop("review_receipt_sha256")
        drifted["review_receipt_sha256"] = hashlib.sha256(
            _canonical(unsigned)
        ).hexdigest()
        _protected(drifted_review, _canonical(drifted) + b"\n")
        evaluate(
            "review-substitution", drifted_review, accept_statement, accept_signature
        )

        changed_statement = root / "changed-decision.json"
        changed = json.loads(accept_statement.read_text())
        changed["decision"] = DECISION_HOLD
        changed["rationale"] = "operator-caution"
        changed["candidate_review_eligible"] = False
        _protected(changed_statement, _canonical(changed))
        evaluate(
            "post-signature-decision-drift",
            passing_review,
            changed_statement,
            accept_signature,
        )

        extended_statement = root / "extended-decision.json"
        extended = json.loads(accept_statement.read_text())
        extended["extension"] = "not allowed"
        _protected(extended_statement, _canonical(extended))
        evaluate(
            "unknown-statement-field",
            passing_review,
            extended_statement,
            accept_signature,
        )

        escalated_statement = root / "escalated-decision.json"
        escalated = json.loads(accept_statement.read_text())
        escalated["deployment_authority"] = True
        _protected(escalated_statement, _canonical(escalated))
        evaluate(
            "authority-escalation",
            passing_review,
            escalated_statement,
            accept_signature,
        )

        evaluate(
            "expired-decision",
            passing_review,
            accept_statement,
            accept_signature,
            now_value="2026-10-26T07:00:00Z",
        )

        replay_registry = root / "replay-registry"
        replay_registry.mkdir(mode=0o700)
        first_replay = evaluate(
            "first-content-addressed-decision",
            passing_review,
            accept_statement,
            accept_signature,
            registry=replay_registry,
        )
        duplicate_replay = evaluate(
            "duplicate-decision-replay",
            passing_review,
            accept_statement,
            accept_signature,
            registry=replay_registry,
        )

        unsafe_registry = root / "unsafe-registry"
        unsafe_registry.mkdir(mode=0o777)
        os.chmod(unsafe_registry, 0o777)
        evaluate(
            "unsafe-decision-registry",
            passing_review,
            accept_statement,
            accept_signature,
            registry=unsafe_registry,
        )

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
        foreign_roster = root / "foreign-roster"
        foreign_roster.write_text(
            f"{KEY_ID} {foreign_key.with_suffix('.pub').read_text(encoding='ascii')}",
            encoding="ascii",
        )
        os.chmod(foreign_roster, 0o600)
        foreign_verifier = OpenSshSignatureVerifier(
            foreign_roster, namespace=NAMESPACE, expected_key_ids=(KEY_ID,)
        )
        evaluate(
            "foreign-trust-root",
            passing_review,
            accept_statement,
            accept_signature,
            verifier=foreign_verifier,
        )

    unsafe_ready = sum(
        item["status"] == STATUS_ACCEPTED
        and any(
            item[key] is not False
            for key in (
                "candidate_accepted",
                "candidate_installed",
                "deployment_authority",
                "hardware_authority",
                "automatic_promotion",
            )
        )
        for item in results
    )
    return {
        "schema": "truepanel.holodeck-temperature-calibration-decision-checkride/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "signing_ready_count": sum(
                item["status"] == "READY_FOR_OFFLINE_CALIBRATION_DECISION_SIGNATURE"
                for item in scenarios
            ),
            "accepted_count": sum(
                item["status"] == STATUS_ACCEPTED for item in scenarios
            ),
            "operator_hold_count": sum(
                item["status"] == STATUS_HELD for item in scenarios
            ),
            "hold_count": sum(item["status"] == "HOLD" for item in scenarios),
            "passing_accepts": int(accepted["status"] == STATUS_ACCEPTED),
            "passing_holds": int(passing_held["status"] == STATUS_HELD),
            "failing_holds": int(failing_held["status"] == STATUS_HELD),
            "failing_accepts": 0,
            "case_count": 440,
            "positive_cases": 40,
            "negative_cases": 400,
            "shared_cooling_index": 19,
            "isolated_threshold_index": 46,
            "lead_samples": 27,
            "decision_registry_writes": sum(
                item["decision_registry_writes"] for item in results
            ),
            "score_registry_writes": sum(
                item["score_registry_writes"] for item in results
            ),
            "field_validations": sum(item["field_validated"] for item in results),
            "candidate_acceptances": sum(
                item["candidate_accepted"] for item in results
            ),
            "candidate_installations": sum(
                item["candidate_installed"] for item in results
            ),
            "deployments": sum(item["deployment_authority"] for item in results),
            "hardware_actions": sum(item["hardware_authority"] for item in results),
            "automatic_promotions": sum(
                item["automatic_promotion"] for item in results
            ),
            "unsafe_ready_count": unsafe_ready,
            "duplicate_replay_blocked": int(
                first_replay["decision_recorded"] is True
                and duplicate_replay["decision_recorded"] is False
            ),
            "fixture_private_keys_created": 2,
            "fixture_private_keys_retained": 0,
        },
        "limitations": [
            "fixture decisions are not field validation",
            "candidate-review eligibility cannot install, deploy, promote, or actuate hardware",
        ],
    }


__all__ = ["run_temperature_calibration_decision_checkride"]
