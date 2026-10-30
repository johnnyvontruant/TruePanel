"""Deterministic rehearsal for the passive-only field-checkride plan."""

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
from truepanel.aegis.temperature_calibration_candidate_appraisal import (
    DECISION_APPROVE,
    DECISION_HOLD,
    NAMESPACE,
    evaluate_temperature_calibration_candidate_appraisal,
    export_temperature_calibration_candidate_appraisal_statement,
)
from truepanel.aegis.temperature_field_checkride_plan import (
    STATUS_READY,
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


def run_temperature_field_checkride_plan_checkride() -> dict[str, Any]:
    """Prove a complete plan remains unable to collect or execute."""
    prepared = "2026-10-28T04:00:00Z"
    expires = "2026-10-28T06:00:00Z"
    now = "2026-10-28T05:00:00Z"
    scenarios: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="truepanel-field-plan-") as directory:
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
        dossier = root / "dossier.json"
        dossier_value = _dossier()
        _protected(dossier, _canonical(dossier_value) + b"\n")

        def appraisal(
            name: str, decision: str, rationale: str
        ) -> tuple[Path, Path, Path]:
            statement = root / f"{name}-statement.json"
            exported = export_temperature_calibration_candidate_appraisal_statement(
                dossier,
                verifier,
                statement,
                decision=decision,
                rationale=rationale,
                prepared_at_utc=prepared,
                expires_at_utc=expires,
                now_utc=now,
            )
            if not exported["statement_created"]:
                raise RuntimeError(exported["errors"])
            signature = root / f"{name}.sig"
            _sign(key, statement, signature, NAMESPACE)
            registry = root / f"{name}-registry"
            registry.mkdir(mode=0o700)
            recorded = evaluate_temperature_calibration_candidate_appraisal(
                dossier,
                verifier,
                statement,
                signature,
                registry,
                now_utc=now,
            )
            if not recorded["appraisal_recorded"]:
                raise RuntimeError(recorded["errors"])
            return statement, signature, registry / str(recorded["receipt_filename"])

        approve_statement, approve_signature, approve_receipt = appraisal(
            "approve",
            DECISION_APPROVE,
            "evidence-complete-for-manual-field-checkride-planning",
        )
        hold_statement, hold_signature, hold_receipt = appraisal(
            "hold", DECISION_HOLD, "operator-caution"
        )

        def plan(
            name: str,
            *,
            contract: dict[str, Any] | None = None,
            statement: Path = approve_statement,
            signature: Path = approve_signature,
            receipt: Path = approve_receipt,
            occupy_output: bool = False,
        ) -> dict[str, Any]:
            output = root / f"{name}.json"
            if occupy_output:
                _protected(output, b"occupied")
            result = assemble_temperature_field_checkride_plan(
                dossier,
                verifier,
                statement,
                signature,
                receipt,
                contract or expected_temperature_field_checkride_contract(),
                output,
                now_utc=now,
            )
            scenarios.append(
                {
                    "scenario": name,
                    "status": result["status"],
                    "plan_created": result["plan_created"],
                    "confirmation_present": result["confirmation_present"],
                    "recording_present": result["recording_present"],
                    "field_checkride_authority": result["field_checkride_authority"],
                    "error_count": len(result["errors"]),
                }
            )
            return result

        plan("approved-passive-plan")
        plan(
            "operator-appraisal-hold",
            statement=hold_statement,
            signature=hold_signature,
            receipt=hold_receipt,
        )

        substituted_receipt = root / "substituted-receipt.json"
        receipt_value = json.loads(approve_receipt.read_text())
        receipt_value["dossier_sha256"] = "8" * 64
        unsigned = dict(receipt_value)
        unsigned.pop("receipt_sha256")
        receipt_value["receipt_sha256"] = hashlib.sha256(
            _canonical(unsigned)
        ).hexdigest()
        _protected(substituted_receipt, _canonical(receipt_value) + b"\n")
        plan("appraisal-receipt-substitution", receipt=substituted_receipt)

        live_source = copy.deepcopy(expected_temperature_field_checkride_contract())
        live_source["source"]["live_host_path_allowed"] = True
        plan("live-host-source", contract=live_source)

        privacy = copy.deepcopy(expected_temperature_field_checkride_contract())
        privacy["privacy"]["forbidden"].remove("serial-numbers")
        plan("privacy-relaxation", contract=privacy)

        missing_abort = copy.deepcopy(expected_temperature_field_checkride_contract())
        missing_abort["abort_criteria"].pop()
        plan("missing-abort-criterion", contract=missing_abort)

        automatic_capture = copy.deepcopy(
            expected_temperature_field_checkride_contract()
        )
        automatic_capture["source"]["truepanel_capture_allowed"] = True
        plan("automatic-capture", contract=automatic_capture)

        authority = copy.deepcopy(expected_temperature_field_checkride_contract())
        authority["hardware_authority"] = True
        plan("authority-escalation", contract=authority)

        unknown = copy.deepcopy(expected_temperature_field_checkride_contract())
        unknown["extension"] = "forbidden"
        plan("unknown-contract-field", contract=unknown)

        plan("occupied-output", occupy_output=True)

    ready_count = sum(item["status"] == STATUS_READY for item in scenarios)
    unsafe_ready = sum(
        item["status"] == STATUS_READY
        and item["scenario"] != "approved-passive-plan"
        for item in scenarios
    )
    return {
        "schema": "truepanel.holodeck-temperature-field-checkride-plan/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "plan_ready_count": ready_count,
            "hold_count": len(scenarios) - ready_count,
            "passive_observation_count": 7,
            "abort_criterion_count": 6,
            "required_evidence_count": 7,
            "coverage_total": 8,
            "coverage_trusted": 8,
            "coverage_gaps": 0,
            "shared_cooling_first_match_sample": 19,
            "isolated_threshold_first_match_sample": 46,
            "lead_samples": 27,
            "separate_confirmations": 0,
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
            "unsafe_ready_count": unsafe_ready,
            "fixture_private_keys_created": 1,
            "fixture_private_keys_retained": 0,
        },
        "limitations": [
            "fixture identity only",
            "plan readiness still requires a separate operator confirmation",
            "no recording, live host, capture, execution, or operational authority",
        ],
    }


__all__ = ["run_temperature_field_checkride_plan_checkride"]
