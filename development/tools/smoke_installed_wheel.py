#!/usr/bin/env python3
"""Exercise an installed TruePanel wheel outside its source checkout."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path


def run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def main() -> int:
    executable = Path(sys.executable).with_name("truepanel")
    if not executable.is_file():
        raise RuntimeError(f"installed truepanel command is missing: {executable}")

    with tempfile.TemporaryDirectory(prefix="truepanel-wheel-smoke-") as directory:
        outside = Path(directory)
        import_check = run(
            [
                sys.executable,
                "-I",
                "-c",
                (
                    "import pathlib, truepanel, truepanel.cli; "
                    "path = pathlib.Path(truepanel.__file__).resolve(); "
                    "assert 'site-packages' in str(path), path; "
                    "import sys; "
                    "assert 'truepanel.holodeck.host_agent' not in sys.modules; "
                    "assert 'truepanel.holodeck.runner' not in sys.modules; "
                    "print(path)"
                ),
            ],
            cwd=outside,
        )
        assert "site-packages" in import_check.stdout

        corpus_check = run(
            [
                sys.executable,
                "-I",
                "-c",
                (
                    "from truepanel.holodeck.aegis_corpus import "
                    "run_black_box_corpus; "
                    "report = run_black_box_corpus(); "
                    "assert report['corpus_size'] == 6; "
                    "assert report['confusion_matrix']['false_positive'] == 0; "
                    "from truepanel.aegis.evidence_gate import "
                    "builtin_lab_evidence_status; "
                    "gate = builtin_lab_evidence_status(); "
                    "assert gate['stage'] == 'lab_calibrated'; "
                    "assert gate['production_validated'] is False"
                ),
            ],
            cwd=outside,
        )
        assert corpus_check.returncode == 0

        hangar_flight_check = run(
            [
                sys.executable,
                "-I",
                "-c",
                (
                    "from truepanel.hangar import load_registry, validate_registry; "
                    "registry = load_registry(); "
                    "assert validate_registry(registry) == (); "
                    "assert len(registry['experiments']) == 31; "
                    "checkride = next(item for item in registry['experiments'] "
                    "if item['id'] == 'TP-EXP-0015'); "
                    "assert checkride['state'] == 'IN_PROGRESS'; "
                    "ground_truth = next(item for item in registry['experiments'] "
                    "if item['id'] == 'TP-EXP-0017'); "
                    "assert ground_truth['state'] == 'COMPLETED'; "
                    "passive = next(item for item in registry['experiments'] "
                    "if item['id'] == 'TP-EXP-0018'); "
                    "assert passive['state'] == 'COMPLETED'; "
                    "from truepanel.holodeck.aegis_passive_providers import "
                    "run_passive_provider_rehearsal; "
                    "passive_proof = run_passive_provider_rehearsal(); "
                    "assert passive_proof['measurements']['negative_holds'] == 3; "
                    "assert passive_proof['measurements']['unsafe_false_ready'] == 0; "
                    "from truepanel.holodeck.aegis_passive_runtime import "
                    "run_passive_runtime_rehearsal; "
                    "runtime_proof = run_passive_runtime_rehearsal(); "
                    "assert runtime_proof['measurements']['negative_holds'] == 4; "
                    "assert runtime_proof['measurements']['unsafe_false_ready'] == 0; "
                    "assert runtime_proof['measurements']['delegate_calls_after_second_observation'] == 3; "
                    "runtime = next(item for item in registry['experiments'] "
                    "if item['id'] == 'TP-EXP-0019'); "
                    "assert runtime['state'] == 'COMPLETED'; "
                    "consequences = next(item for item in registry['experiments'] "
                    "if item['id'] == 'TP-EXP-0020'); "
                    "assert consequences['state'] == 'COMPLETED'; "
                    "stable_identity = next(item for item in registry['experiments'] "
                    "if item['id'] == 'TP-EXP-0021'); "
                    "assert stable_identity['state'] == 'COMPLETED'; "
                    "blind_spot = next(item for item in registry['experiments'] "
                    "if item['id'] == 'TP-EXP-0022'); "
                    "assert blind_spot['state'] == 'COMPLETED'; "
                    "from truepanel.holodeck.aegis_temperature_blind_spot import "
                    "run_temperature_blind_spot_checkride; "
                    "blind_spot_proof = run_temperature_blind_spot_checkride(); "
                    "assert blind_spot_proof['measurements']['false_overheating_claims'] == 0; "
                    "assert blind_spot_proof['measurements']['cross_drive_false_correlations'] == 0; "
                    "appraisal = next(item for item in registry['experiments'] "
                    "if item['id'] == 'TP-EXP-0023'); "
                    "assert appraisal['state'] == 'COMPLETED'; "
                    "from truepanel.holodeck.aegis_temperature_coverage_appraisal import "
                    "run_temperature_coverage_appraisal_checkride; "
                    "appraisal_proof = run_temperature_coverage_appraisal_checkride(); "
                    "assert appraisal_proof['measurements']['review_ready_count'] == 1; "
                    "assert appraisal_proof['measurements']['unsafe_ready_count'] == 0; "
                    "acceptance = next(item for item in registry['experiments'] "
                    "if item['id'] == 'TP-EXP-0024'); "
                    "assert acceptance['state'] == 'COMPLETED'; "
                    "from truepanel.holodeck.aegis_temperature_development_acceptance import "
                    "run_temperature_development_acceptance_checkride; "
                    "acceptance_proof = run_temperature_development_acceptance_checkride(); "
                    "assert acceptance_proof['measurements']['development_accepted_count'] == 1; "
                    "assert acceptance_proof['measurements']['runtime_acceptances'] == 0; "
                    "authenticated = next(item for item in registry['experiments'] "
                    "if item['id'] == 'TP-EXP-0026'); "
                    "assert authenticated['state'] == 'COMPLETED'; "
                    "from truepanel.holodeck.aegis_temperature_authenticated_acceptance import "
                    "run_temperature_authenticated_acceptance_checkride; "
                    "authenticated_proof = run_temperature_authenticated_acceptance_checkride(); "
                    "assert authenticated_proof['measurements']['authenticated_development_acceptance_count'] == 1; "
                    "assert authenticated_proof['measurements']['fixture_private_keys_retained'] == 0; "
                    "assert authenticated_proof['measurements']['runtime_acceptances'] == 0; "
                    "signing_kit = next(item for item in registry['experiments'] "
                    "if item['id'] == 'TP-EXP-0027'); "
                    "assert signing_kit['state'] == 'COMPLETED'; "
                    "from truepanel.holodeck.aegis_temperature_signing_kit import "
                    "run_temperature_signing_kit_checkride; "
                    "kit_proof = run_temperature_signing_kit_checkride(); "
                    "assert kit_proof['measurements']['signing_ready_count'] == 1; "
                    "assert kit_proof['measurements']['hold_count'] == 10; "
                    "assert kit_proof['measurements']['private_key_inputs_accepted'] == 0; "
                    "assert kit_proof['measurements']['signer_invocations_by_truepanel'] == 0; "
                    "field_checkride = next(item for item in registry['experiments'] "
                    "if item['id'] == 'TP-EXP-0028'); "
                    "assert field_checkride['state'] == 'COMPLETED'; "
                    "from truepanel.holodeck.aegis_temperature_field_checkride import "
                    "run_temperature_field_checkride; "
                    "field_proof = run_temperature_field_checkride(); "
                    "assert field_proof['measurements']['simulation_rehearsal_passed_count'] == 1; "
                    "assert field_proof['measurements']['field_observation_review_ready_count'] == 1; "
                    "assert field_proof['measurements']['false_field_validation_count'] == 0; "
                    "recording_intake = next(item for item in registry['experiments'] "
                    "if item['id'] == 'TP-EXP-0029'); "
                    "assert recording_intake['state'] == 'COMPLETED'; "
                    "from truepanel.holodeck.aegis_temperature_recording_intake import "
                    "run_temperature_recording_intake_checkride; "
                    "intake_proof = run_temperature_recording_intake_checkride(); "
                    "assert intake_proof['measurements']['simulation_rehearsal_passed_count'] == 1; "
                    "assert intake_proof['measurements']['field_observation_review_ready_count'] == 1; "
                    "assert intake_proof['measurements']['unsafe_ready_count'] == 0; "
                    "assert intake_proof['measurements']['capture_operations'] == 0; "
                    "field_review = next(item for item in registry['experiments'] "
                    "if item['id'] == 'TP-EXP-0030'); "
                    "assert field_review['state'] == 'COMPLETED'; "
                    "from truepanel.holodeck.aegis_temperature_field_review_receipt import "
                    "run_temperature_field_review_receipt_checkride; "
                    "review_proof = run_temperature_field_review_receipt_checkride(); "
                    "assert review_proof['measurements']['signing_ready_count'] == 1; "
                    "assert review_proof['measurements']['field_review_accepted_count'] == 2; "
                    "assert review_proof['measurements']['unsafe_ready_count'] == 0; "
                    "assert review_proof['measurements']['signer_invocations_by_truepanel'] == 0; "
                    "calibration_admission = next(item for item in registry['experiments'] "
                    "if item['id'] == 'TP-EXP-0031'); "
                    "assert calibration_admission['state'] == 'COMPLETED'; "
                    "from truepanel.holodeck.aegis_temperature_calibration_admission import "
                    "run_temperature_calibration_admission_checkride; "
                    "admission_proof = run_temperature_calibration_admission_checkride(); "
                    "assert admission_proof['measurements']['signing_ready_count'] == 1; "
                    "assert admission_proof['measurements']['admitted_count'] == 2; "
                    "assert admission_proof['measurements']['corpus_writes'] == 0; "
                    "assert admission_proof['measurements']['unsafe_ready_count'] == 0; "
                    "calibration_corpus = next(item for item in registry['experiments'] "
                    "if item['id'] == 'TP-EXP-0032'); "
                    "assert calibration_corpus['state'] == 'COMPLETED'; "
                    "from truepanel.holodeck.aegis_temperature_calibration_corpus import "
                    "run_temperature_calibration_corpus_checkride; "
                    "corpus_proof = run_temperature_calibration_corpus_checkride(); "
                    "assert corpus_proof['measurements']['imported_count'] == 1; "
                    "assert corpus_proof['measurements']['hold_count'] == 8; "
                    "assert corpus_proof['measurements']['committed_case_directories'] == 1; "
                    "assert corpus_proof['measurements']['field_validations'] == 0; "
                    "from truepanel.glass_cockpit import "
                    "benchmark, validate_corpus; "
                    "assert validate_corpus() == (); "
                    "assert benchmark()['winner'] == 'B'; "
                    "from truepanel.aegis.flight_director import "
                    "run_flight_director_proof; "
                    "proof = run_flight_director_proof(); "
                    "assert proof['measurements']['detection_lead_samples'] == 27; "
                    "assert proof['repair_verification_signature']['outcome'] == 'passed'; "
                    "assert proof['control_authority'] is False; "
                    "from truepanel.aegis.checkride import "
                    "evaluate_pre_service_clearance, "
                    "run_storage_recovery_rehearsals; "
                    "rehearsals = run_storage_recovery_rehearsals(); "
                    "assert len(rehearsals) == 6; "
                    "assert all(item['hardware_isolated'] for item in rehearsals); "
                    "receipt = evaluate_pre_service_clearance({}, "
                    "incident_id='fixture', identity={}, topology={}); "
                    "assert receipt['status'] == 'HOLD'; "
                    "assert receipt['storage_write_authority'] is False; "
                    "from truepanel.holodeck.aegis_attestations import "
                    "run_recovery_attestation_rehearsal; "
                    "ground = run_recovery_attestation_rehearsal(); "
                    "assert ground['measurements']['negative_holds'] == 6; "
                    "assert ground['measurements']['unsafe_false_ready'] == 0; "
                    "assert ground['control_authority'] is False"
                ),
            ],
            cwd=outside,
        )
        assert hangar_flight_check.returncode == 0

        field_smoke = run(
            [
                str(executable),
                "holodeck",
                "field-smoke",
                str(outside / "field-workflow"),
            ],
            cwd=outside,
        )
        field_receipt = json.loads(field_smoke.stdout)
        assert field_receipt["stage"] == "lab_calibrated"
        assert field_receipt["production_validated"] is False
        assert field_receipt["hardware_isolated"] is True
        assert field_receipt["control_authority"] is False

        reported = run([str(executable), "version"], cwd=outside)
        assert f"Version: {version('truepanel')}" in reported.stdout

        simulated = run(
            [
                str(executable),
                "holodeck",
                "run",
                "battlestation",
                "--steps",
                "1",
                "--json",
            ],
            cwd=outside,
        )
        state = json.loads(simulated.stdout)
        assert state["system"]["hostname"] == "HoloDeck-BattleStation"
        assert state["read_only"] is True

        injected = run(
            [
                str(executable),
                "holodeck",
                "inject",
                "fan_stall",
                "channel=1",
            ],
            cwd=outside,
        )
        fault = json.loads(injected.stdout)
        assert fault["fans"]["fan_channels"][0]["rpm"] == 0

        checked = run(
            [
                str(executable),
                "holodeck",
                "check",
                "battlestation",
                "--steps",
                "2",
                "--json",
            ],
            cwd=outside,
        )
        assert json.loads(checked.stdout)["passed"] is True

        recording = outside / "incident.jsonl"
        recording.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "privacy": "sanitized",
                    "captured_at": 10,
                    "sequence": 1,
                    "telemetry": {},
                    "lcd": {},
                    "fan": {
                        "fan_channels": [
                            {
                                "number": 1,
                                "rpm": 0,
                                "stalled": True,
                                "healthy": True,
                                "alarm": False,
                            }
                        ]
                    },
                    "storage": {},
                    "alerts": [],
                    "buttons": {},
                    "mission_control": {},
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        replayed = run(
            [
                str(executable),
                "holodeck",
                "replay",
                str(recording),
                "--json",
            ],
            cwd=outside,
        )
        assert len(replayed.stdout.splitlines()) == 1

        output = outside / "compiled.json"
        compiled = run(
            [
                str(executable),
                "holodeck",
                "compile-incident",
                str(recording),
                "--invariant",
                "cooling.stalled_not_healthy",
                "--output",
                str(output),
            ],
            cwd=outside,
        )
        manifest = json.loads(compiled.stdout)
        artifact = json.loads(output.read_text(encoding="utf-8"))
        assert manifest == artifact["manifest"]
        assert manifest["minimized_frame_count"] == 1
        assert manifest["executable_code_generated"] is False

    print("PASS: installed wheel, HoloDeck, AEGIS, HANGAR, and Flight Director smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
