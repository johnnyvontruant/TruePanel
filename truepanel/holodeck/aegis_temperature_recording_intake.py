"""Adversarial proof for protected temperature recording intake."""

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
from truepanel.aegis.temperature_recording_intake import (
    evaluate_temperature_recording_intake,
)
from truepanel.aegis.temperature_signing_kit import export_temperature_signing_kit
from truepanel.holodeck.aegis_temperature_field_checkride import (
    _frames,
    _sign,
    _storage,
)
from truepanel.holodeck.aegis_temperature_signing_kit import _materials


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _write_recording(path: Path, frames: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            f"{json.dumps(frame, sort_keys=True, separators=(',', ':'))}\n"
            for frame in frames
        ),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def run_temperature_recording_intake_checkride() -> dict[str, Any]:
    """Prove bounded snapshot, privacy, authentication, and authority boundaries."""

    candidate, appraisal, confirmation = _materials()
    # The pinned development confirmation expires shortly after this instant;
    # use the same deterministic clock as its predecessor rehearsal.
    now = "2026-10-12T04:30:00Z"
    scenarios: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="truepanel-temperature-intake-") as directory:
        root = Path(directory).resolve()
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
        invalid_signature = root / "invalid.sig"
        invalid_signature.write_text("not an ssh signature\n", encoding="ascii")
        os.chmod(invalid_signature, 0o600)

        def run(
            name: str,
            frames: list[dict[str, Any]],
            *,
            content: str | None = None,
            unsafe_mode: bool = False,
            symlink: bool = False,
            **changes: Any,
        ) -> None:
            recording = root / f"{len(scenarios):02d}-{name}.jsonl"
            if content is None:
                _write_recording(recording, frames)
            else:
                recording.write_text(content, encoding="utf-8")
                os.chmod(recording, 0o600)
            if unsafe_mode:
                os.chmod(recording, 0o666)
            intake_path = recording
            if symlink:
                intake_path = root / f"{recording.stem}-link.jsonl"
                intake_path.symlink_to(recording)
            defaults = {
                "evidence_source": "holodeck-deterministic",
                "operator_opt_in": False,
                "incident_reviewed": False,
                "signature_path": str(signature),
            }
            defaults.update(changes)
            result = evaluate_temperature_recording_intake(
                candidate,
                appraisal,
                confirmation,
                str(kit),
                defaults.pop("signature_path"),
                verifier,
                intake_path,
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

        baseline = _frames()
        run("protected-deterministic-recording", baseline)
        run(
            "reviewed-opt-in-field-recording",
            baseline,
            evidence_source="operator-opt-in-field",
            operator_opt_in=True,
            incident_reviewed=True,
        )
        run(
            "invalid-operator-signature",
            baseline,
            signature_path=str(invalid_signature),
        )
        raw_identity = deepcopy(baseline)
        raw_identity[0]["storage"]["devices"][0]["serial"] = "raw-serial"
        run("unsanitized-identifier", raw_identity)
        run("group-world-writable-recording", baseline, unsafe_mode=True)
        run("symlinked-recording", baseline, symlink=True)
        run("malformed-json", baseline, content="{not-json}\n")
        run("extra-frame", [*baseline, deepcopy(baseline[-1])])
        incomplete = deepcopy(baseline)
        incomplete[3]["storage"] = _storage(missing=True)
        run("incomplete-recovery", incomplete)
        identity_drift = deepcopy(baseline)
        identity_drift[2]["storage"] = _storage(missing=False, drift=True)
        run("member-identity-drift", identity_drift)
        run("ungoverned-source", baseline, evidence_source="live-direct")
        run(
            "field-without-outcome-review",
            baseline,
            evidence_source="operator-opt-in-field",
            operator_opt_in=True,
        )
        paths_retained = sum(str(root) in json.dumps(item) for item in results)
        fixture_private_keys_created = 1

    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0029",
        "scenario": "aegis-protected-temperature-recording-intake",
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
            "unsafe_ready_count": sum(
                item["status"] != "HOLD" for item in results[2:]
            ),
            "source_paths_retained": paths_retained,
            "capture_operations": sum(
                item["capture_performed"] is not False for item in results
            ),
            "private_key_inputs": sum(
                item["private_key_accepted"] is not False for item in results
            ),
            "fixture_private_keys_created": fixture_private_keys_created,
            "fixture_private_keys_retained": 0,
            "production_keys": 0,
            "field_validations": 0,
            "candidate_acceptances": 0,
            "candidate_installations": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
        },
        "comparison": {
            "aegis": "authenticates and snapshots one bounded protected recording before replaying the four-frame recovery proof",
            "generic_tailers": "optimize for continuous watching and checkpoints rather than an immutable operator-reviewed evidence handoff",
            "result": "one replaceable standard-library intake with no capture, tailing, private-key, or control surface",
        },
        "temporary_fixture_removed": not root.exists(),
    }
    report["evidence_sha256"] = _sha256(report)
    return report


__all__ = ["run_temperature_recording_intake_checkride"]
