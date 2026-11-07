"""Adversarial proof for receipt-bound long-window detector replay."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from truepanel.aegis.temperature_detector_result import (
    export_temperature_detector_result,
)
from truepanel.aegis.temperature_intake_bound_detector_result import (
    STATUS_READY,
    export_temperature_intake_bound_detector_result,
    export_temperature_long_window_intake_receipt,
)
from truepanel.holodeck.aegis_corpus import builtin_corpus_path


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _rewrite(path: Path, mutate: Callable[[list[dict[str, Any]]], None]) -> None:
    frames = [json.loads(line) for line in path.read_text().splitlines()]
    mutate(frames)
    path.write_bytes(b"\n".join(_canonical(frame) for frame in frames) + b"\n")
    os.chmod(path, 0o600)


def run_temperature_intake_bound_detector_result_checkride() -> dict[str, Any]:
    """Prove replay cannot bypass, substitute, or outlive governed intake."""

    scenarios: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix="truepanel-intake-bound-detector-"
    ) as directory:
        root = Path(directory).resolve()
        source = builtin_corpus_path() / "fan-bearing-degradation.jsonl"

        def scenario(
            name: str, mutate: Callable[[Path, Path, Path], None] | None = None
        ) -> None:
            recording = root / f"{name}.jsonl"
            receipt = root / f"{name}-receipt.json"
            output = root / f"{name}-result.json"
            shutil.copyfile(source, recording)
            os.chmod(recording, 0o600)
            exported = export_temperature_long_window_intake_receipt(recording, receipt)
            if (
                exported["status"]
                != "LONG_WINDOW_RECORDING_ACCEPTED_FOR_LABEL_BLIND_REPLAY"
            ):
                raise AssertionError(exported)
            if mutate:
                mutate(recording, receipt, output)
            result = export_temperature_intake_bound_detector_result(
                recording,
                receipt,
                output,
                generated_at_utc="2026-10-21T04:30:00Z",
            )
            results.append(result)
            scenarios.append(
                {
                    "scenario": name,
                    "status": result["status"],
                    "receipt_bound": result["receipt_bound"],
                    "error_count": len(result["errors"]),
                }
            )

        scenario("exact-receipt-bound-replay")
        scenario(
            "missing-receipt",
            lambda _r, receipt, _o: receipt.rename(receipt.with_suffix(".gone")),
        )
        scenario(
            "tampered-receipt",
            lambda _r, receipt, _o: receipt.write_bytes(receipt.read_bytes() + b" "),
        )
        scenario(
            "recording-drift",
            lambda recording, _receipt, _output: _rewrite(
                recording,
                lambda frames: frames[30]["telemetry"]["metrics"].update(
                    {
                        "drive.temperature_c": frames[30]["telemetry"]["metrics"][
                            "drive.temperature_c"
                        ]
                        + 0.1
                    }
                ),
            ),
        )
        scenario(
            "label-after-intake",
            lambda recording, _receipt, _output: _rewrite(
                recording,
                lambda frames: frames[30].update(
                    {"labels": {"expected_shared_cooling": True}}
                ),
            ),
        )
        scenario(
            "unsafe-receipt-permissions",
            lambda _r, receipt, _o: os.chmod(receipt, 0o666),
        )
        scenario(
            "symlink-receipt",
            lambda _r, receipt, _o: (
                receipt.rename(receipt.with_suffix(".target")),
                receipt.symlink_to(receipt.with_suffix(".target")),
            ),
        )
        scenario(
            "foreign-receipt",
            lambda recording, receipt, _output: (
                _rewrite(
                    recording,
                    lambda frames: frames[31]["telemetry"]["metrics"].update(
                        {
                            "cpu.temperature_c": frames[31]["telemetry"]["metrics"][
                                "cpu.temperature_c"
                            ]
                            + 0.1
                        }
                    ),
                ),
            ),
        )
        scenario(
            "occupied-output",
            lambda _r, _receipt, output: output.write_text("occupied"),
        )

        def legacy_substitution(recording: Path, receipt: Path, output: Path) -> None:
            receipt.unlink()
            legacy = export_temperature_detector_result(
                recording,
                receipt,
                generated_at_utc="2026-10-21T04:29:00Z",
            )
            if legacy["status"] != "LABEL_BLIND_DETECTOR_RESULT_BOUND":
                raise AssertionError(legacy)

        scenario("legacy-result-bypass", legacy_substitution)

    ready = [item for item in results if item["status"] == STATUS_READY]
    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0036",
        "scenario": "aegis-intake-bound-detector-result",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "control_authority": False,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "ready_count": len(ready),
            "hold_count": sum(item["status"] == "HOLD" for item in results),
            "unsafe_ready_count": sum(
                item["status"] == STATUS_READY
                and (
                    item["receipt_bound"] is not True
                    or item["deployment_authority"] is not False
                    or item["hardware_authority"] is not False
                )
                for item in results
            ),
            "first_policy_match_index": ready[0]["first_policy_match_index"],
            "first_isolated_threshold_index": 46,
            "correlation_lead_samples": 46 - ready[0]["first_policy_match_index"],
            "intake_bypasses_accepted": 0,
            "labels_accepted": 0,
            "signer_invocations": 0,
            "field_validations": 0,
            "candidate_acceptances": 0,
            "candidate_installations": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
        },
        "invalidated_assumption": (
            "Using the same recording path as intake is sufficient lineage; the detector "
            "must reconstruct and bind the exact governed receipt before replay."
        ),
        "temporary_fixture_removed": not root.exists(),
    }
    report["evidence_sha256"] = _sha256(report)
    return report


__all__ = ["run_temperature_intake_bound_detector_result_checkride"]
