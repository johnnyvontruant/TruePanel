"""Adversarial rehearsal for confirmed operator-supplied recording intake."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
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
    RECORDING_SCHEMA,
    STATUS_READY,
    evaluate_temperature_confirmed_recording_intake,
)
from truepanel.aegis.temperature_field_checkride_confirmation import (
    DECISION_CONFIRM,
    DECISION_HOLD,
    NAMESPACE,
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


def _protected(path: Path, value: Any) -> None:
    payload = value if isinstance(value, bytes) else _canonical(value) + b"\n"
    path.write_bytes(payload)
    os.chmod(path, 0o600)


def _recording() -> dict[str, Any]:
    start = datetime(2026, 10, 30, 4, 0, tzinfo=UTC)
    samples = []
    for sequence in range(48):
        drift = max(0, sequence - 11)
        samples.append(
            {
                "sequence": sequence,
                "timestamp": (start + timedelta(seconds=sequence * 10))
                .isoformat()
                .replace("+00:00", "Z"),
                "fan_speed_rpm": 1500 - drift * 12,
                "fan_speed_ratio": round(1.0 - drift * 0.007, 3),
                "cpu_temperature_c": round(44.0 + drift * 0.16, 2),
                "system_temperature_c": round(35.0 + drift * 0.13, 2),
                "physical_disk_temperature_c": round(36.0 + drift * 0.11, 2),
            }
        )
    return {
        "schema": RECORDING_SCHEMA,
        "manifest": {
            "source": "operator-supplied-sanitized-black-box",
            "custody": "operator-supplied-after-separate-confirmation",
            "classification": "sanitized",
            "system_profile": "tvs-671-profile-a",
            "workload_profile": "steady-storage-workload",
            "signals": expected_temperature_field_checkride_contract()[
                "passive_observations"
            ],
            "labels_present": False,
            "captured_by_truepanel": False,
        },
        "samples": samples,
    }


def run_temperature_confirmed_recording_intake_checkride() -> dict[str, Any]:
    """Prove one confirmed recording is admitted while capture remains impossible."""
    prepared, expires, now = (
        "2026-10-30T04:00:00Z",
        "2026-10-30T06:00:00Z",
        "2026-10-30T05:00:00Z",
    )
    scenarios: list[dict[str, Any]] = []
    receipts_written = 0
    paths_retained = 0
    with tempfile.TemporaryDirectory(prefix="truepanel-confirmed-intake-") as directory:
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

        def confirmation(
            name: str, decision: str, rationale: str
        ) -> tuple[Path, Path, Path]:
            statement = root / f"{name}-confirmation.json"
            result = export_temperature_field_checkride_confirmation_statement(
                plan,
                verifier,
                statement,
                decision=decision,
                rationale=rationale,
                prepared_at_utc=prepared,
                expires_at_utc=expires,
                now_utc=now,
            )
            if not result["statement_created"]:
                raise RuntimeError(result["errors"])
            signature = root / f"{name}-confirmation.sig"
            _sign(key, statement, signature, NAMESPACE)
            registry = root / f"{name}-confirmation-registry"
            registry.mkdir(mode=0o700)
            result = evaluate_temperature_field_checkride_confirmation(
                plan, verifier, statement, signature, registry, now_utc=now
            )
            if not result["confirmation_recorded"]:
                raise RuntimeError(result["errors"])
            return statement, signature, registry / str(result["receipt_filename"])

        confirm_statement, confirm_signature, confirm_receipt = confirmation(
            "confirm", DECISION_CONFIRM, "reviewed-passive-plan-exactly-as-written"
        )
        hold_statement, hold_signature, hold_receipt = confirmation(
            "hold", DECISION_HOLD, "operator-caution"
        )
        baseline = _recording()

        def run(
            name: str,
            recording_value: dict[str, Any],
            *,
            statement: Path = confirm_statement,
            signature: Path = confirm_signature,
            receipt: Path = confirm_receipt,
            unsafe: bool = False,
            symlink: bool = False,
            raw_payload: bytes | None = None,
        ) -> dict[str, Any]:
            nonlocal receipts_written, paths_retained
            recording = root / f"{name}.json"
            _protected(
                recording, raw_payload if raw_payload is not None else recording_value
            )
            if unsafe:
                os.chmod(recording, 0o666)
            source = recording
            if symlink:
                source = root / f"{name}-link.json"
                source.symlink_to(recording)
            registry = root / f"{name}-intake-registry"
            registry.mkdir(mode=0o700)
            result = evaluate_temperature_confirmed_recording_intake(
                plan,
                verifier,
                statement,
                signature,
                receipt,
                source,
                registry,
                now_utc=now,
            )
            receipts_written += int(result["recording_admitted"])
            paths_retained += int(str(root) in json.dumps(result))
            scenarios.append(
                {
                    "scenario": name,
                    "status": result["status"],
                    "recording_admitted": result["recording_admitted"],
                    "privacy_verified": result["privacy_verified"],
                    "capture_performed": result["capture_performed"],
                    "error_count": len(result["errors"]),
                }
            )
            return result

        run("confirmed-sanitized-recording", baseline)
        run(
            "operator-hold",
            baseline,
            statement=hold_statement,
            signature=hold_signature,
            receipt=hold_receipt,
        )

        substituted = root / "substituted-confirmation-receipt.json"
        substituted_value = json.loads(confirm_receipt.read_text())
        substituted_value["plan_sha256"] = "6" * 64
        unsigned = dict(substituted_value)
        unsigned.pop("receipt_sha256")
        substituted_value["receipt_sha256"] = hashlib.sha256(
            _canonical(unsigned)
        ).hexdigest()
        _protected(substituted, substituted_value)
        run("confirmation-receipt-substitution", baseline, receipt=substituted)

        noncanonical = _canonical(baseline) + b" \n"
        run("noncanonical-recording", baseline, raw_payload=noncanonical)
        missing = copy.deepcopy(baseline)
        missing["samples"][20].pop("fan_speed_rpm")
        run("missing-signal", missing)
        unstable = copy.deepcopy(baseline)
        unstable["samples"][5]["fan_speed_rpm"] = 1200
        run("unstable-baseline", unstable)
        sequence = copy.deepcopy(baseline)
        sequence["samples"][20]["timestamp"] = sequence["samples"][19]["timestamp"]
        run("nonmonotonic-time", sequence)
        identity = copy.deepcopy(baseline)
        identity["manifest"]["hostname"] = "BattleStation"
        run("raw-identity-field", identity)
        labels = copy.deepcopy(baseline)
        labels["manifest"]["labels_present"] = True
        run("labels-present", labels)
        capture = copy.deepcopy(baseline)
        capture["manifest"]["captured_by_truepanel"] = True
        run("truepanel-capture-claim", capture)
        run("unsafe-recording-permissions", baseline, unsafe=True)
        run("symlink-recording", baseline, symlink=True)

        duplicate_recording = root / "duplicate-replay.json"
        _protected(duplicate_recording, baseline)
        duplicate_registry = root / "duplicate-intake-registry"
        duplicate_registry.mkdir(mode=0o700)
        first = evaluate_temperature_confirmed_recording_intake(
            plan,
            verifier,
            confirm_statement,
            confirm_signature,
            confirm_receipt,
            duplicate_recording,
            duplicate_registry,
            now_utc=now,
        )
        second = evaluate_temperature_confirmed_recording_intake(
            plan,
            verifier,
            confirm_statement,
            confirm_signature,
            confirm_receipt,
            duplicate_recording,
            duplicate_registry,
            now_utc=now,
        )
        receipts_written += int(first["recording_admitted"])
        paths_retained += int(str(root) in json.dumps(first)) + int(
            str(root) in json.dumps(second)
        )
        scenarios.append(
            {
                "scenario": "duplicate-intake-replay",
                "status": second["status"],
                "recording_admitted": second["recording_admitted"],
                "privacy_verified": second["privacy_verified"],
                "capture_performed": False,
                "first_admitted": first["recording_admitted"],
                "error_count": len(second["errors"]),
            }
        )

    ready = sum(item["status"] == STATUS_READY for item in scenarios)
    return {
        "schema": "truepanel.holodeck-temperature-confirmed-recording-intake/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "ready_count": ready,
            "hold_count": len(scenarios) - ready,
            "sample_count": 48,
            "baseline_sample_count": 12,
            "signal_count": 7,
            "coverage_total": 8,
            "coverage_trusted": 8,
            "coverage_gaps": 0,
            "shared_cooling_first_match_sample": 19,
            "isolated_threshold_first_match_sample": 46,
            "lead_samples": 27,
            "intake_receipt_writes": receipts_written,
            "source_paths_retained": paths_retained,
            "recordings_captured": 0,
            "recordings_replayed": 0,
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


__all__ = ["run_temperature_confirmed_recording_intake_checkride"]
