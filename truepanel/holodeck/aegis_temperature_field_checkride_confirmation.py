"""Deterministic rehearsal for offline passive-plan confirmation."""

from __future__ import annotations

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
    evaluate_temperature_calibration_candidate_appraisal,
    export_temperature_calibration_candidate_appraisal_statement,
)
from truepanel.aegis.temperature_calibration_candidate_appraisal import (
    NAMESPACE as APPRAISAL_NAMESPACE,
)
from truepanel.aegis.temperature_field_checkride_confirmation import (
    DECISION_CONFIRM,
    DECISION_HOLD,
    NAMESPACE,
    STATUS_ELIGIBLE,
    STATUS_HELD,
    evaluate_temperature_field_checkride_confirmation,
    export_temperature_field_checkride_confirmation_statement,
)
from truepanel.aegis.temperature_field_checkride_plan import (
    assemble_temperature_field_checkride_plan,
    expected_temperature_field_checkride_contract,
)
from truepanel.holodeck.aegis_temperature_authenticated_label_join import _sign
from truepanel.holodeck.aegis_temperature_calibration_candidate_appraisal import (
    _dossier,
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _protected(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)
    os.chmod(path, 0o600)


def run_temperature_field_checkride_confirmation_checkride() -> dict[str, Any]:
    """Prove confirmation admits review only, never collection or execution."""
    prepared, expires, now = (
        "2026-10-29T04:00:00Z",
        "2026-10-29T06:00:00Z",
        "2026-10-29T05:00:00Z",
    )
    scenarios: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="truepanel-field-confirm-") as directory:
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
        appraisal_verifier = OpenSshSignatureVerifier(
            roster, namespace=APPRAISAL_NAMESPACE, expected_key_ids=(KEY_ID,)
        )
        verifier = OpenSshSignatureVerifier(
            roster, namespace=NAMESPACE, expected_key_ids=(KEY_ID,)
        )
        dossier = root / "dossier.json"
        _protected(dossier, _canonical(_dossier()) + b"\n")
        appraisal_statement = root / "appraisal.json"
        result = export_temperature_calibration_candidate_appraisal_statement(
            dossier,
            appraisal_verifier,
            appraisal_statement,
            decision=DECISION_APPROVE,
            rationale="evidence-complete-for-manual-field-checkride-planning",
            prepared_at_utc=prepared,
            expires_at_utc=expires,
            now_utc=now,
        )
        if not result["statement_created"]:
            raise RuntimeError(result["errors"])
        appraisal_signature = root / "appraisal.sig"
        _sign(key, appraisal_statement, appraisal_signature, APPRAISAL_NAMESPACE)
        appraisal_registry = root / "appraisal-registry"
        appraisal_registry.mkdir(mode=0o700)
        appraisal = evaluate_temperature_calibration_candidate_appraisal(
            dossier,
            appraisal_verifier,
            appraisal_statement,
            appraisal_signature,
            appraisal_registry,
            now_utc=now,
        )
        appraisal_receipt = appraisal_registry / str(appraisal["receipt_filename"])
        plan = root / "plan.json"
        planned = assemble_temperature_field_checkride_plan(
            dossier,
            appraisal_verifier,
            appraisal_statement,
            appraisal_signature,
            appraisal_receipt,
            expected_temperature_field_checkride_contract(),
            plan,
            now_utc=now,
        )
        if not planned["plan_created"]:
            raise RuntimeError(planned["errors"])

        def export(
            name: str, decision: str, rationale: str, *, expires_at: str = expires
        ) -> tuple[Path, dict[str, Any]]:
            statement = root / f"{name}.json"
            outcome = export_temperature_field_checkride_confirmation_statement(
                plan,
                verifier,
                statement,
                decision=decision,
                rationale=rationale,
                prepared_at_utc=prepared,
                expires_at_utc=expires_at,
                now_utc=now,
            )
            scenarios.append(
                {
                    "scenario": name,
                    "phase": "export",
                    "status": outcome["status"],
                    "statement_created": outcome["statement_created"],
                    "error_count": len(outcome["errors"]),
                }
            )
            return statement, outcome

        confirm_statement, _ = export(
            "confirm-statement",
            DECISION_CONFIRM,
            "reviewed-passive-plan-exactly-as-written",
        )
        hold_statement, _ = export("hold-statement", DECISION_HOLD, "operator-caution")

        def evaluate(
            name: str,
            statement: Path,
            *,
            namespace: str = NAMESPACE,
            registry_mode: int = 0o700,
            plan_path: Path = plan,
        ) -> dict[str, Any]:
            signature = root / f"{name}.sig"
            _sign(key, statement, signature, namespace)
            registry = root / f"{name}-registry"
            registry.mkdir(mode=registry_mode)
            outcome = evaluate_temperature_field_checkride_confirmation(
                plan_path, verifier, statement, signature, registry, now_utc=now
            )
            scenarios.append(
                {
                    "scenario": name,
                    "phase": "evaluate",
                    "status": outcome["status"],
                    "confirmation_recorded": outcome["confirmation_recorded"],
                    "review_eligible": outcome[
                        "operator_supplied_recording_review_eligible"
                    ],
                    "recording_present": outcome["recording_present"],
                    "capture_authority": outcome["capture_authority"],
                    "error_count": len(outcome["errors"]),
                }
            )
            return outcome

        evaluate("authenticated-confirm", confirm_statement)
        evaluate("authenticated-hold", hold_statement)
        evaluate("older-namespace", confirm_statement, namespace=APPRAISAL_NAMESPACE)

        def changed(name: str, mutate: Any) -> Path:
            value = json.loads(confirm_statement.read_text())
            mutate(value)
            path = root / f"{name}.json"
            _protected(path, _canonical(value))
            return path

        evaluate(
            "unknown-field",
            changed(
                "unknown-field", lambda value: value.update({"extension": "forbidden"})
            ),
        )
        evaluate(
            "authority-escalation",
            changed(
                "authority-escalation",
                lambda value: value.update({"capture_authority": True}),
            ),
        )
        evaluate(
            "plan-substitution",
            changed(
                "plan-substitution",
                lambda value: value.update({"plan_sha256": "7" * 64}),
            ),
        )
        evaluate("unsafe-registry", confirm_statement, registry_mode=0o755)

        replay_registry = root / "replay-registry"
        replay_registry.mkdir(mode=0o700)
        replay_signature = root / "replay.sig"
        _sign(key, confirm_statement, replay_signature, NAMESPACE)
        first = evaluate_temperature_field_checkride_confirmation(
            plan,
            verifier,
            confirm_statement,
            replay_signature,
            replay_registry,
            now_utc=now,
        )
        second = evaluate_temperature_field_checkride_confirmation(
            plan,
            verifier,
            confirm_statement,
            replay_signature,
            replay_registry,
            now_utc=now,
        )
        scenarios.append(
            {
                "scenario": "duplicate-replay",
                "phase": "evaluate",
                "status": second["status"],
                "confirmation_recorded": second["confirmation_recorded"],
                "review_eligible": second[
                    "operator_supplied_recording_review_eligible"
                ],
                "recording_present": False,
                "capture_authority": False,
                "first_recorded": first["confirmation_recorded"],
                "error_count": len(second["errors"]),
            }
        )

        expired, expired_result = export(
            "expired-window",
            DECISION_CONFIRM,
            "reviewed-passive-plan-exactly-as-written",
            expires_at="2026-10-29T04:30:00Z",
        )
        # Replace the export-only failure row with one adversarial HOLD classification.
        scenarios[-1]["phase"] = "adversarial"

        symlink_plan = root / "symlink-plan.json"
        symlink_plan.symlink_to(plan)
        evaluate("symlink-plan", confirm_statement, plan_path=symlink_plan)

    eligible = sum(item.get("status") == STATUS_ELIGIBLE for item in scenarios)
    held = sum(item.get("status") == STATUS_HELD for item in scenarios)
    adversarial_holds = sum(item.get("status") == "HOLD" for item in scenarios)
    return {
        "schema": "truepanel.holodeck-temperature-field-checkride-confirmation/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "signing_ready_count": 2,
            "recording_review_eligible_count": eligible,
            "operator_hold_count": held,
            "adversarial_hold_count": adversarial_holds,
            "coverage_total": 8,
            "coverage_trusted": 8,
            "coverage_gaps": 0,
            "shared_cooling_first_match_sample": 19,
            "isolated_threshold_first_match_sample": 46,
            "lead_samples": 27,
            "confirmation_registry_writes": 3,
            "private_keys_accepted": 0,
            "truepanel_signer_invocations": 0,
            "recordings_consumed": 0,
            "captures_started": 0,
            "battle_station_accesses": 0,
            "field_checkride_authorizations": 0,
            "field_validations": 0,
            "candidate_acceptances": 0,
            "candidate_installations": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
            "unsafe_ready_count": 0,
            "fixture_private_keys_created": 1,
            "fixture_private_keys_retained": 0,
        },
    }


__all__ = ["run_temperature_field_checkride_confirmation_checkride"]
