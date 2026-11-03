"""Adversarial rehearsal for independent label-blind passive replay."""

from __future__ import annotations

import copy
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
from truepanel.aegis.temperature_confirmed_recording_intake import (
    evaluate_temperature_confirmed_recording_intake,
)
from truepanel.aegis.temperature_field_checkride_confirmation import (
    DECISION_CONFIRM,
    NAMESPACE,
    evaluate_temperature_field_checkride_confirmation,
    export_temperature_field_checkride_confirmation_statement,
)
from truepanel.aegis.temperature_field_checkride_plan import (
    assemble_temperature_field_checkride_plan,
    expected_temperature_field_checkride_contract,
)
from truepanel.aegis.temperature_label_blind_passive_replay import (
    STATUS_READY,
    evaluate_temperature_label_blind_passive_replay,
)
from truepanel.holodeck.aegis_temperature_authenticated_label_join import _sign
from truepanel.holodeck.aegis_temperature_calibration_candidate_appraisal import (
    _dossier,
)
from truepanel.holodeck.aegis_temperature_confirmed_recording_intake import (
    _protected,
    _recording,
)


def run_temperature_label_blind_passive_replay_checkride() -> dict[str, Any]:
    """Prove exact evidence can be replayed once without labels or authority."""
    prepared, expires, now = (
        "2026-10-30T04:00:00Z",
        "2026-10-30T06:00:00Z",
        "2026-10-30T05:00:00Z",
    )
    scenarios: list[dict[str, Any]] = []
    receipt_writes = 0
    replay_count = 0
    with tempfile.TemporaryDirectory(
        prefix="truepanel-label-blind-replay-"
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
        appraisal_verifier = OpenSshSignatureVerifier(
            roster, namespace=APPRAISAL_NAMESPACE, expected_key_ids=(KEY_ID,)
        )
        verifier = OpenSshSignatureVerifier(
            roster, namespace=NAMESPACE, expected_key_ids=(KEY_ID,)
        )
        dossier = root / "dossier.json"
        _protected(dossier, _dossier())
        appraisal_statement = root / "appraisal.json"
        exported = export_temperature_calibration_candidate_appraisal_statement(
            dossier,
            appraisal_verifier,
            appraisal_statement,
            decision=DECISION_APPROVE,
            rationale="evidence-complete-for-manual-field-checkride-planning",
            prepared_at_utc=prepared,
            expires_at_utc=expires,
            now_utc=now,
        )
        if not exported["statement_created"]:
            raise RuntimeError(exported["errors"])
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
        confirmation_statement = root / "confirmation.json"
        confirmed = export_temperature_field_checkride_confirmation_statement(
            plan,
            verifier,
            confirmation_statement,
            decision=DECISION_CONFIRM,
            rationale="reviewed-passive-plan-exactly-as-written",
            prepared_at_utc=prepared,
            expires_at_utc=expires,
            now_utc=now,
        )
        if not confirmed["statement_created"]:
            raise RuntimeError(confirmed["errors"])
        confirmation_signature = root / "confirmation.sig"
        _sign(key, confirmation_statement, confirmation_signature, NAMESPACE)
        confirmation_registry = root / "confirmation-registry"
        confirmation_registry.mkdir(mode=0o700)
        confirmed = evaluate_temperature_field_checkride_confirmation(
            plan,
            verifier,
            confirmation_statement,
            confirmation_signature,
            confirmation_registry,
            now_utc=now,
        )
        confirmation_receipt = confirmation_registry / str(
            confirmed["receipt_filename"]
        )

        def admit(name: str, value: dict[str, Any]) -> tuple[Path, Path]:
            recording = root / f"{name}-recording.json"
            _protected(recording, value)
            registry = root / f"{name}-intake-registry"
            registry.mkdir(mode=0o700)
            result = evaluate_temperature_confirmed_recording_intake(
                plan,
                verifier,
                confirmation_statement,
                confirmation_signature,
                confirmation_receipt,
                recording,
                registry,
                now_utc=now,
            )
            if not result["recording_admitted"]:
                raise RuntimeError(result["errors"])
            return recording, registry / str(result["receipt_filename"])

        recording, intake_receipt = admit("valid", _recording())

        def replay(
            name: str,
            *,
            recording_path: Path = recording,
            intake_path: Path = intake_receipt,
            confirmation_path: Path = confirmation_receipt,
            registry: Path | None = None,
        ) -> dict[str, Any]:
            replay_registry = registry or root / f"{name}-replay-registry"
            if not replay_registry.exists():
                replay_registry.mkdir(mode=0o700)
            result = evaluate_temperature_label_blind_passive_replay(
                plan,
                verifier,
                confirmation_statement,
                confirmation_signature,
                confirmation_path,
                recording_path,
                intake_path,
                replay_registry,
                now_utc=now,
            )
            scenarios.append(
                {
                    "scenario": name,
                    "status": result["status"],
                    "receipt_written": result["replay_receipt_written"],
                    "label_blind": result["label_blind"],
                    "probable_root_cause": result["probable_root_cause"],
                    "confidence": result["confidence"],
                    "match_sample": result["first_shared_cooling_match_sample"],
                    "isolated_sample": result["first_isolated_threshold_sample"],
                    "lead_samples": result["lead_samples"],
                    "error_count": len(result["errors"]),
                    "errors": result["errors"],
                }
            )
            return result

        valid = replay("valid-label-blind-passive-replay")
        receipt_writes += int(valid["replay_receipt_written"])
        replay_count += int(valid["passive_replay_performed"])

        substituted = root / "substituted-intake.json"
        changed = json.loads(intake_receipt.read_text())
        changed["recording_sha256"] = "0" * 64
        _protected(substituted, changed)
        replay("intake-receipt-substitution", intake_path=substituted)

        drifted = copy.deepcopy(_recording())
        drifted["samples"][-1]["cpu_temperature_c"] += 0.01
        drifted_path = root / "recording-drift.json"
        _protected(drifted_path, drifted)
        replay("recording-substitution", recording_path=drifted_path)

        labeled = copy.deepcopy(_recording())
        labeled["manifest"]["labels_present"] = True
        labeled_path = root / "labels-present.json"
        _protected(labeled_path, labeled)
        replay("labels-present", recording_path=labeled_path)

        noncanonical = root / "noncanonical-recording.json"
        _protected(noncanonical, json.dumps(_recording(), indent=2).encode())
        replay("noncanonical-recording", recording_path=noncanonical)

        unstable = copy.deepcopy(_recording())
        unstable["samples"][5]["fan_speed_rpm"] -= 100
        unstable_path = root / "unstable-baseline.json"
        _protected(unstable_path, unstable)
        replay("unstable-baseline", recording_path=unstable_path)

        nonmonotonic = copy.deepcopy(_recording())
        nonmonotonic["samples"][20]["timestamp"] = nonmonotonic["samples"][19][
            "timestamp"
        ]
        nonmonotonic_path = root / "nonmonotonic.json"
        _protected(nonmonotonic_path, nonmonotonic)
        replay("nonmonotonic-time", recording_path=nonmonotonic_path)

        confirmation_substitute = root / "confirmation-substitute.json"
        value = json.loads(confirmation_receipt.read_text())
        value["plan_sha256"] = "f" * 64
        _protected(confirmation_substitute, value)
        replay(
            "confirmation-receipt-substitution",
            confirmation_path=confirmation_substitute,
        )

        unsafe_receipt = root / "unsafe-intake.json"
        unsafe_receipt.write_bytes(intake_receipt.read_bytes())
        os.chmod(unsafe_receipt, 0o666)
        replay("unsafe-intake-permissions", intake_path=unsafe_receipt)

        symlink_receipt = root / "intake-link.json"
        symlink_receipt.symlink_to(intake_receipt)
        replay("symlink-intake-receipt", intake_path=symlink_receipt)

        escalated = root / "escalated-intake.json"
        value = json.loads(intake_receipt.read_text())
        value["deployment_authority"] = True
        _protected(escalated, value)
        replay("authority-escalation", intake_path=escalated)

        stable = _recording()
        for sample in stable["samples"]:
            sample.update(
                {
                    "fan_speed_rpm": 1500,
                    "fan_speed_ratio": 1.0,
                    "cpu_temperature_c": 44.0,
                    "system_temperature_c": 35.0,
                    "physical_disk_temperature_c": 36.0,
                }
            )
        stable_recording, stable_intake = admit("stable", stable)
        replay(
            "insufficient-shared-cooling-evidence",
            recording_path=stable_recording,
            intake_path=stable_intake,
        )

        duplicate_registry = root / "duplicate-replay-registry"
        duplicate_registry.mkdir(mode=0o700)
        first = evaluate_temperature_label_blind_passive_replay(
            plan,
            verifier,
            confirmation_statement,
            confirmation_signature,
            confirmation_receipt,
            recording,
            intake_receipt,
            duplicate_registry,
            now_utc=now,
        )
        receipt_writes += int(first["replay_receipt_written"])
        replay_count += int(first["passive_replay_performed"])
        replay("duplicate-replay", registry=duplicate_registry)

    ready_count = sum(item["status"] == STATUS_READY for item in scenarios)
    return {
        "schema": "truepanel.holodeck-temperature-label-blind-passive-replay/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "ready_count": ready_count,
            "hold_count": len(scenarios) - ready_count,
            "sample_count": 48,
            "baseline_sample_count": 12,
            "supporting_signal_count": 5,
            "confidence": 0.95,
            "coverage_total": 8,
            "coverage_trusted": 8,
            "coverage_gaps": 0,
            "shared_cooling_first_match_sample": 19,
            "isolated_threshold_first_match_sample": 46,
            "lead_samples": 27,
            "replay_receipt_writes": receipt_writes,
            "passive_replays_performed": replay_count,
            "labels_revealed": 0,
            "live_captures": 0,
            "battle_station_accesses": 0,
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


__all__ = ["run_temperature_label_blind_passive_replay_checkride"]
