"""Adversarial proof for governed long-window Black Box intake."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from truepanel.aegis.temperature_long_window_intake import (
    STATUS_READY,
    evaluate_temperature_long_window_intake,
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


def run_temperature_long_window_intake_checkride() -> dict[str, Any]:
    """Prove long-window intake accepts evidence, never outcomes or authority."""

    scenarios: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="truepanel-long-window-") as directory:
        root = Path(directory).resolve()
        source = builtin_corpus_path() / "fan-bearing-degradation.jsonl"

        def scenario(
            name: str,
            mutate: Callable[[Path], None] | None = None,
            *,
            symlink: bool = False,
        ) -> None:
            path = root / f"{name}.jsonl"
            shutil.copyfile(source, path)
            os.chmod(path, 0o600)
            target = path
            if mutate:
                mutate(path)
            if symlink:
                link = root / f"{name}-link.jsonl"
                link.symlink_to(path)
                target = link
            result = evaluate_temperature_long_window_intake(target)
            results.append(result)
            scenarios.append(
                {
                    "scenario": name,
                    "status": result["status"],
                    "frame_count": result["frame_count"],
                    "error_count": len(result["errors"]),
                }
            )

        scenario("bounded-label-blind-window")
        scenario("insufficient-window", lambda path: path.write_bytes(b"\n".join(path.read_bytes().splitlines()[:12]) + b"\n"))
        scenario("symlink-substitution", symlink=True)
        scenario("unsafe-permissions", lambda path: os.chmod(path, 0o666))
        scenario("malformed-json", lambda path: path.write_bytes(b"{\n"))
        scenario(
            "label-leakage",
            lambda path: _rewrite(path, lambda frames: frames[20].update({"labels": {"expected_shared_cooling": True}})),
        )
        scenario(
            "missing-required-metric",
            lambda path: _rewrite(path, lambda frames: frames[20]["telemetry"]["metrics"].pop("fan.rpm")),
        )
        scenario(
            "sequence-reordering",
            lambda path: _rewrite(path, lambda frames: frames[20].update({"sequence": 19})),
        )
        scenario(
            "timestamp-reordering",
            lambda path: _rewrite(path, lambda frames: frames[20].update({"captured_at": 19.0})),
        )
        scenario(
            "unstable-baseline",
            lambda path: _rewrite(path, lambda frames: frames[5]["telemetry"]["metrics"].update({"fan.rpm": 800.0})),
        )

    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0035",
        "scenario": "aegis-governed-long-window-intake",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "control_authority": False,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "accepted_count": sum(item["status"] == STATUS_READY for item in results),
            "hold_count": sum(item["status"] == "HOLD" for item in results),
            "unsafe_ready_count": sum(
                item["status"] == STATUS_READY
                and (
                    item["labels_present"] is not False
                    or item["deployment_authority"] is not False
                    or item["hardware_authority"] is not False
                )
                for item in results
            ),
            "accepted_frame_count": next(
                item["frame_count"] for item in results if item["status"] == STATUS_READY
            ),
            "accepted_baseline_frames": next(
                item["baseline_frame_count"] for item in results if item["status"] == STATUS_READY
            ),
            "labels_accepted": 0,
            "capture_operations": 0,
            "tail_operations": 0,
            "checkpoint_writes": 0,
            "field_validations": 0,
            "candidate_acceptances": 0,
            "candidate_installations": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
        },
        "invalidated_assumption": (
            "A minimum frame count alone proves a useful calibration window; "
            "the intake must also prove exact ordering, required signal shape, "
            "a stable baseline, and absence of outcome labels."
        ),
        "temporary_fixture_removed": not root.exists(),
    }
    report["evidence_sha256"] = _sha256(report)
    return report


__all__ = ["run_temperature_long_window_intake_checkride"]
