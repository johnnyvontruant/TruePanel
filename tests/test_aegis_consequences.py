from __future__ import annotations

import json
from pathlib import Path

import yaml

from truepanel.aegis import AegisReliabilityEngine, correlate_consequences
from truepanel.guidance import guidance_for_snapshot
from truepanel.holodeck.aegis_consequences import run_consequence_correlation_rehearsal
from truepanel.sentinel import (
    attach_consequence_summaries,
    attach_recovery_references,
    run_sentinel_rehearsal,
)
from truepanel.web.sentinel_snapshot import SentinelSnapshotService

ROOT = Path(__file__).resolve().parents[1]


def _incident(*devices):
    return {
        "confidence": 0.62,
        "supporting_signals": [
            {
                "source": "verified_detector",
                "signal": "storage.smart_warning",
                "evidence": {"device": device},
            }
            for device in devices
        ],
    }


def _sentinel(device="/dev/sdc"):
    return {
        "read_only": True,
        "control_authority": False,
        "explanations": [
            {
                "read_only": True,
                "control_authority": False,
                "source_device": device,
                "known_impact": [
                    {
                        "node_id": "pool:HDDs",
                        "kind": "pool",
                        "label": "HDDs",
                        "state": "ONLINE",
                        "depth": 2,
                        "via": ["disk:/dev/sdc", "vdev:HDDs:raidz1-0", "pool:HDDs"],
                    },
                    {
                        "node_id": "application:radarr",
                        "kind": "application",
                        "label": "Radarr",
                        "state": "RUNNING",
                        "depth": 4,
                        "via": [
                            "disk:/dev/sdc",
                            "vdev:HDDs:raidz1-0",
                            "pool:HDDs",
                            "dataset:HDDs/Movies",
                            "application:radarr",
                        ],
                    },
                    {
                        "node_id": "backup:movie",
                        "kind": "backup_evidence",
                        "label": "Movie backup",
                        "state": "VERIFIED",
                        "depth": 5,
                        "via": ["disk:/dev/sdc", "pool:HDDs", "backup:movie"],
                    },
                ],
                "unknowns": ["A second backup provider is not observed."],
                "recovery": {"references": [{"code": "storage.smart_warning"}]},
            }
        ],
    }


def test_exact_device_joins_proved_context_without_changing_confidence():
    incident = _incident("/dev/sdc")
    before = incident["confidence"]

    context = correlate_consequences(incident, _sentinel())

    assert context["state"] == "PROVED"
    assert context["source_device"] == "/dev/sdc"
    assert context["counts"] == {
        "proved_objects": 3,
        "storage_objects": 1,
        "applications": 1,
        "running_applications": 1,
        "cargo": 0,
        "verified_backup_evidence": 1,
    }
    assert context["diagnostic_confidence_unchanged"] is True
    assert context["confidence_effect"] == "none"
    assert incident["confidence"] == before
    assert "does not mean down" in context["language_guard"]


def test_mismatch_ambiguity_and_malformed_paths_fail_closed():
    mismatch = correlate_consequences(_incident("/dev/sdd"), _sentinel())
    ambiguous = correlate_consequences(_incident("/dev/sdc", "/dev/sdd"), _sentinel())
    unsafe = _sentinel()
    unsafe["explanations"][0]["control_authority"] = True
    malformed = _sentinel()
    malformed["explanations"][0]["known_impact"][0]["via"][0] = "disk:/dev/sdz"

    assert mismatch["state"] == "HOLD"
    assert mismatch["source_device"] == "/dev/sdd"
    assert ambiguous["state"] == "HOLD"
    assert ambiguous["source_device"] is None
    assert correlate_consequences(_incident("/dev/sdc"), unsafe)["state"] == "HOLD"
    assert correlate_consequences(_incident("/dev/sdc"), malformed)["state"] == "HOLD"


def test_reliability_engine_consumes_existing_sentinel_snapshot_without_polling():
    payload = {
        "timestamp": 1,
        "operator_guidance": [
            {
                "code": "storage.smart_warning",
                "title": "SMART warning",
                "summary": "Drive health evidence is abnormal.",
                "immediate_actions": [{"detail": "Review the exact drive evidence."}],
                "runtime": {"phase": "diagnose", "evidence": {"device": "/dev/sdc"}},
                "recovery": {"verification": {"status": "pending"}},
            }
        ],
        "fans": {},
        "storage": {"smart": [{"device": "/dev/sdc", "reallocated": 3}]},
        "network": [],
        "sentinel": _sentinel(),
    }

    result = AegisReliabilityEngine().observe(payload)
    context = result["active_incident"]["consequence_context"]

    assert context["state"] == "PROVED"
    assert context["counts"]["applications"] == 1
    assert context["read_only"] is True
    assert context["control_authority"] is False


def test_accepted_sentinel_holodeck_scenario_reaches_aegis_by_exact_device():
    fixture = yaml.safe_load(
        (
            ROOT / "tests/fixtures/scenarios/sentinel-bay3-storage-impact.yaml"
        ).read_text()
    )
    snapshot = fixture["snapshot"]
    sentinel = run_sentinel_rehearsal(fixture)["sentinel"]
    SentinelSnapshotService._attach_live_explanations(sentinel)
    guidance = guidance_for_snapshot(snapshot)
    attach_recovery_references(sentinel, guidance)
    attach_consequence_summaries(sentinel)
    snapshot.update(
        {"timestamp": 1, "operator_guidance": guidance, "sentinel": sentinel}
    )

    reliability = AegisReliabilityEngine().observe(snapshot)
    context = reliability["active_incident"]["consequence_context"]

    assert [item["code"] for item in guidance] == ["storage.smart_warning"]
    assert context["source_device"] == fixture["expect"]["source_device"]
    assert context["counts"]["proved_objects"] == len(fixture["expect"]["reachable"])
    assert context["counts"]["running_applications"] == 1
    assert context["counts"]["verified_backup_evidence"] == 1
    assert reliability["active_incident"]["confidence"] == 0.62


def test_holodeck_rehearsal_and_preserved_evidence_are_exact():
    report = run_consequence_correlation_rehearsal()

    assert report["measurements"] == {
        "scenarios": 5,
        "proved_contexts": 1,
        "hold_contexts": 4,
        "false_joins": 0,
        "diagnostic_confidence_before": 0.62,
        "diagnostic_confidence_after": 0.62,
        "diagnostic_confidence_increases": 0,
        "additional_telemetry_reads": 0,
        "recovery_actions": 0,
    }
    assert report["control_authority"] is False
    evidence = ROOT / "docs/evidence/aegis-consequence-correlation-v1.json"
    assert json.loads(evidence.read_text()) == report


def test_mission_control_context_is_mobile_and_does_not_claim_outage():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()

    assert "PROVED DEPENDENCY REACH" in source
    assert "IMPACT TOPOLOGY · HOLD" in source
    assert "Diagnostic confidence unchanged" in source
    assert "does not prove an outage" in source
    assert "@media(max-width:760px){.ag-consequence{grid-template-columns:1fr}" in source
    assert "setInterval" not in source
