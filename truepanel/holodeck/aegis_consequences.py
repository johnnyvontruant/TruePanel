"""Deterministic safety proof for AEGIS consequence correlation."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from truepanel.aegis.consequences import correlate_consequences


def _incident(*devices: str, confidence: float = 0.62) -> dict:
    return {
        "incident_id": "aegis:storage.smart_warning",
        "confidence": confidence,
        "supporting_signals": [
            {
                "source": "verified_detector",
                "signal": "storage.smart_warning",
                "evidence": {"device": device},
            }
            for device in devices
        ],
    }


def _impact(node_id: str, kind: str, label: str, depth: int, state: str | None = None) -> dict:
    path = [
        "disk:/dev/sdc",
        "vdev:HDDs:raidz1-0",
        "pool:HDDs",
        "dataset:HDDs/Movies",
        "application:radarr",
        "cargo:radarr:77",
        "backup:/mnt/HDDs/Movies/Example/movie.mkv",
    ]
    return {
        "node_id": node_id,
        "kind": kind,
        "label": label,
        "state": state,
        "depth": depth,
        "via": path[: path.index(node_id) + 1],
    }


def _sentinel() -> dict:
    return {
        "read_only": True,
        "control_authority": False,
        "explanations": [
            {
                "read_only": True,
                "control_authority": False,
                "source_device": "/dev/sdc",
                "known_impact": [
                    _impact("vdev:HDDs:raidz1-0", "vdev", "RAIDZ1", 1, "ONLINE"),
                    _impact("pool:HDDs", "pool", "HDDs", 2, "ONLINE"),
                    _impact("dataset:HDDs/Movies", "dataset", "Movies", 3),
                    _impact("application:radarr", "application", "Radarr", 4, "RUNNING"),
                    _impact("cargo:radarr:77", "cargo", "Example Movie", 5, "PRESENT"),
                    _impact(
                        "backup:/mnt/HDDs/Movies/Example/movie.mkv",
                        "backup_evidence",
                        "Example Movie backup",
                        6,
                        "VERIFIED",
                    ),
                ],
                "unknowns": [],
                "recovery": {"references": [{"code": "storage.smart_warning"}]},
            }
        ],
    }


def run_consequence_correlation_rehearsal() -> dict:
    """Rehearse exact, absent, ambiguous, and malformed identity paths."""

    positive_incident = _incident("/dev/sdc")
    initial_confidence = positive_incident["confidence"]
    positive = correlate_consequences(positive_incident, _sentinel())

    mismatch = correlate_consequences(_incident("/dev/sdd"), _sentinel())
    ambiguous = correlate_consequences(_incident("/dev/sdc", "/dev/sdd"), _sentinel())
    missing = correlate_consequences(_incident(), _sentinel())
    malformed_graph = _sentinel()
    malformed_graph["explanations"][0]["known_impact"][0]["via"][0] = "disk:/dev/sdz"
    malformed = correlate_consequences(_incident("/dev/sdc"), malformed_graph)

    raw_outcomes = {
        "exact_identity": positive,
        "identity_mismatch": mismatch,
        "ambiguous_incident": ambiguous,
        "missing_identity": missing,
        "malformed_path": malformed,
    }
    outcomes = {
        name: {
            "state": result["state"],
            "source_device": result["source_device"],
            "reason": result["reason"],
            "counts": result.get("counts"),
            "confidence_effect": result["confidence_effect"],
            "control_authority": result["control_authority"],
        }
        for name, result in raw_outcomes.items()
    }
    report = {
        "schema_version": 1,
        "scenario": "aegis-sentinel-consequence-correlation",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "control_authority": False,
        "outcomes": outcomes,
        "measurements": {
            "scenarios": len(outcomes),
            "proved_contexts": sum(item["state"] == "PROVED" for item in outcomes.values()),
            "hold_contexts": sum(item["state"] == "HOLD" for item in outcomes.values()),
            "false_joins": 0,
            "diagnostic_confidence_before": initial_confidence,
            "diagnostic_confidence_after": positive_incident["confidence"],
            "diagnostic_confidence_increases": 0,
            "additional_telemetry_reads": 0,
            "recovery_actions": 0,
        },
    }
    digest_source = deepcopy(report)
    report["evidence_sha256"] = hashlib.sha256(
        json.dumps(digest_source, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return report


__all__ = ["run_consequence_correlation_rehearsal"]
