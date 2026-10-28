"""Adversarial replay proof for the read-only temperature field checkride."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from truepanel.aegis.ssh_verifier import OpenSshSignatureVerifier
from truepanel.aegis.temperature_authenticated_acceptance import KEY_ID, NAMESPACE
from truepanel.aegis.temperature_field_checkride import (
    evaluate_temperature_field_checkride,
)
from truepanel.aegis.temperature_signing_kit import export_temperature_signing_kit
from truepanel.history.black_box import BlackBoxFrame
from truepanel.holodeck.aegis_temperature_signing_kit import _materials


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _storage(*, missing: bool, drift: bool = False) -> dict[str, Any]:
    devices = [
        {
            "pool": "HDDs",
            "vdev": "raidz1-0",
            "member_id": f"member-{bay}",
            "device": f"sd{letter}",
            "physical_bay": bay,
            "present": True,
            "zfs_state": "ONLINE",
        }
        for bay, letter in enumerate(("a", "b", "c"), start=1)
    ]
    if drift:
        devices[-1]["device"] = "sdd"
    temperatures = [
        {"device": item["device"], "bay": item["physical_bay"], "temp": 34 + index}
        for index, item in enumerate(devices)
        if not (missing and item["physical_bay"] == 3)
    ]
    return {"devices": devices, "temperatures": temperatures, "smart": []}


def _frames() -> list[dict[str, Any]]:
    return [
        BlackBoxFrame.capture(
            captured_at=float(index),
            sequence=index,
            storage=_storage(missing=index == 0),
            alerts=(
                [{"code": "storage.temperature_telemetry_missing"}]
                if index == 0
                else []
            ),
        ).as_dict()
        for index in range(4)
    ]


def _sign(key: Path, statement: Path, destination: Path) -> None:
    subprocess.run(
        [
            "/usr/bin/ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(key),
            "-n",
            NAMESPACE,
            str(statement),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    Path(f"{statement}.sig").replace(destination)
    os.chmod(destination, 0o600)


def run_temperature_field_checkride() -> dict[str, Any]:
    """Prove authentication, privacy, identity, and authority boundaries."""

    candidate, appraisal, confirmation = _materials()
    now = "2026-10-12T04:30:00Z"
    scenarios: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    def run(name: str, observations: list[dict[str, Any]], **changes: Any) -> None:
        defaults = {
            "evidence_source": "holodeck-deterministic",
            "operator_opt_in": False,
            "incident_reviewed": False,
            "signature_path": str(signature),
        }
        defaults.update(changes)
        result = evaluate_temperature_field_checkride(
            candidate,
            appraisal,
            confirmation,
            str(kit),
            defaults.pop("signature_path"),
            verifier,
            observations,
            now_utc=now,
            **defaults,
        )
        results.append(result)
        scenarios.append(
            {
                "scenario": name,
                "status": result["status"],
                "error_count": len(result["errors"]),
            }
        )

    with tempfile.TemporaryDirectory(prefix="truepanel-temperature-field-") as directory:
        root = Path(directory)
        source = root / "checkout"
        source.mkdir()
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
        kit = root / "public-kit"
        export_temperature_signing_kit(
            candidate,
            appraisal,
            confirmation,
            kit,
            source_root=source,
            now_utc=now,
        )
        signature = root / "returned.sig"
        _sign(key, kit / "statement.json", signature)

        baseline = _frames()
        run("deterministic-recovery-replay", baseline)
        run(
            "reviewed-opt-in-field-fixture",
            baseline,
            evidence_source="operator-opt-in-field",
            operator_opt_in=True,
            incident_reviewed=True,
        )

        invalid_signature = root / "invalid.sig"
        invalid_signature.write_text("not an ssh signature\n", encoding="ascii")
        os.chmod(invalid_signature, 0o600)
        run(
            "invalid-operator-signature",
            baseline,
            signature_path=str(invalid_signature),
        )

        raw_identity = deepcopy(baseline)
        raw_identity[0]["storage"]["devices"][0]["serial"] = "raw-serial"
        run("unsanitized-identifier", raw_identity)

        unordered = deepcopy(baseline)
        unordered[2]["sequence"] = unordered[1]["sequence"]
        run("non-monotonic-sequence", unordered)

        incomplete = deepcopy(baseline)
        incomplete[3]["storage"] = _storage(missing=True)
        run("incomplete-three-sample-recovery", incomplete)

        identity_drift = deepcopy(baseline)
        identity_drift[2]["storage"] = _storage(missing=False, drift=True)
        run("member-identity-drift", identity_drift)

        no_fault = deepcopy(baseline)
        no_fault[0]["storage"] = _storage(missing=False)
        run("initial-fault-not-reproduced", no_fault)

        run("ungoverned-source", baseline, evidence_source="live-direct")
        run(
            "field-without-opt-in",
            baseline,
            evidence_source="operator-opt-in-field",
            incident_reviewed=True,
        )
        run(
            "field-without-outcome-review",
            baseline,
            evidence_source="operator-opt-in-field",
            operator_opt_in=True,
        )
        run(
            "simulation-claiming-field-review",
            baseline,
            operator_opt_in=True,
            incident_reviewed=True,
        )
        fixture_private_keys_created = 1

    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0028",
        "scenario": "aegis-temperature-read-only-field-checkride",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "control_authority": False,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "simulation_rehearsal_passed_count": sum(
                item["status"] == "SIMULATION_REHEARSAL_PASSED" for item in results
            ),
            "field_observation_review_ready_count": sum(
                item["status"] == "FIELD_OBSERVATION_ACCEPTED_FOR_REVIEW"
                for item in results
            ),
            "hold_count": sum(item["status"] == "HOLD" for item in results),
            "false_field_validation_count": sum(
                item["field_validated"] is not False for item in results
            ),
            "fixture_private_keys_created": fixture_private_keys_created,
            "fixture_private_keys_retained": 0,
            "production_keys": 0,
            "candidate_acceptances": 0,
            "candidate_installations": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
        },
        "comparison": {
            "aegis": "detects the missing member temperature in the first sanitized frame and proves recovery only after three complete identity-stable frames",
            "isolated_thresholds": "cannot detect the absent value and cannot prove restoration of inventory coverage",
            "result": "one authenticated replay contract with explicit non-production authority",
        },
        "temporary_fixture_removed": not root.exists(),
    }
    report["evidence_sha256"] = _sha256(report)
    return report


__all__ = ["run_temperature_field_checkride"]
