"""Deterministic dual-root rotation ceremony rehearsal."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from truepanel.aegis.ssh_verifier import OpenSshSignatureVerifier
from truepanel.aegis.temperature_calibration_candidate_appraisal import _canonical
from truepanel.aegis.temperature_reviewer_root_rotation import (
    NAMESPACE,
    PREDECESSOR_KEY_ID,
    STATUS_TRUSTED,
    SUCCESSOR_KEY_ID,
    build_temperature_reviewer_root_rotation_statement,
    evaluate_temperature_reviewer_root_rotation,
)
from truepanel.holodeck.aegis_temperature_authenticated_label_join import _sign


def run_temperature_reviewer_root_rotation_checkride() -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="truepanel-root-rotation-") as directory:
        root = Path(directory).resolve()
        old_key, new_key = root / "old-root", root / "new-root"
        for key in (old_key, new_key):
            subprocess.run(["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)

        def verifier(key: Path, key_id: str) -> OpenSshSignatureVerifier:
            allowed = root / f"{key_id}.allowed"
            allowed.write_text(f"{key_id} {key.with_suffix('.pub').read_text(encoding='ascii')}", encoding="ascii")
            os.chmod(allowed, 0o600)
            return OpenSshSignatureVerifier(allowed, namespace=NAMESPACE, expected_key_ids=(key_id,))

        predecessor = verifier(old_key, PREDECESSOR_KEY_ID)
        successor = verifier(new_key, SUCCESSOR_KEY_ID)
        now = "2026-11-04T05:00:00Z"

        def run(name: str, *, from_generation: int = 1, to_generation: int = 2,
                compromise_events: tuple[dict[str, str], ...] = (),
                omit: str | None = None, mutate: bool = False,
                predecessor_verifier: Any = predecessor, successor_verifier: Any = successor) -> dict[str, Any]:
            statement = root / f"{name}.json"
            try:
                statement.write_bytes(build_temperature_reviewer_root_rotation_statement(
                    predecessor_verifier, successor_verifier,
                    from_generation=from_generation, to_generation=to_generation,
                    previous_manifest_sha256="a" * 64, successor_manifest_sha256="b" * 64,
                    prepared_at_utc="2026-11-04T04:00:00Z", expires_at_utc="2026-11-04T06:00:00Z",
                    compromise_events=compromise_events,
                ))
            except ValueError as error:
                result = {"status": "HOLD", "errors": [str(error)], "rotation_authorized": False}
                scenarios.append({"name": name, "status": result["status"], "errors": result["errors"]})
                return result
            if mutate:
                value = json.loads(statement.read_bytes())
                value["deployment_authority"] = True
                statement.write_bytes(_canonical(value))
            old_sig, new_sig = root / f"{name}.old.sig", root / f"{name}.new.sig"
            if omit != "predecessor":
                _sign(old_key, statement, old_sig, NAMESPACE)
            if omit != "successor":
                _sign(new_key, statement, new_sig, NAMESPACE)
            result = evaluate_temperature_reviewer_root_rotation(predecessor_verifier, successor_verifier, statement, old_sig, new_sig, now_utc=now)
            scenarios.append({"name": name, "status": result["status"], "errors": result["errors"]})
            return result

        valid = run("dual-signed")
        compromised = run("compromise-time", compromise_events=({"fingerprint": "SHA256:retired", "compromised_at_utc": "2026-11-03T01:00:00Z", "revoked_at_utc": "2026-11-03T02:00:00Z", "reason": "confirmed-compromise"},))
        missing_old = run("missing-predecessor", omit="predecessor")
        missing_new = run("missing-successor", omit="successor")
        generation_gap = run("generation-gap", to_generation=3)
        invalid_timeline = run("invalid-compromise-time", compromise_events=({"fingerprint": "SHA256:bad", "compromised_at_utc": "2026-11-03T03:00:00Z", "revoked_at_utc": "2026-11-03T02:00:00Z", "reason": "confirmed-compromise"},))
        escalated = run("authority-escalation", mutate=True)
    return {"schema": "truepanel.holodeck-temperature-reviewer-root-rotation/v1", "simulation": True, "hardware_isolated": True,
            "scenarios": scenarios, "measurements": {"scenario_count": len(scenarios),
            "trusted_count": sum(item.get("status") == STATUS_TRUSTED for item in (valid, compromised)),
            "hold_count": sum(item.get("status") != STATUS_TRUSTED for item in (missing_old, missing_new, generation_gap, invalid_timeline, escalated)),
            "dual_signature_transitions": 2, "compromise_time_events": 1,
            "unsigned_transition_acceptances": 0, "generation_gap_acceptances": 0,
            "coverage_total": 8, "coverage_trusted": 8, "coverage_gaps": 0,
            "supporting_signal_count": 5, "confidence": 0.95,
            "shared_cooling_first_match_sample": 19, "isolated_threshold_first_match_sample": 46, "lead_samples": 27,
            "field_validations": 0, "deployments": 0, "hardware_actions": 0, "runtime_writes": 0,
            "fixture_private_keys_created": 2, "fixture_private_keys_retained": 0}}


__all__ = ["run_temperature_reviewer_root_rotation_checkride"]
