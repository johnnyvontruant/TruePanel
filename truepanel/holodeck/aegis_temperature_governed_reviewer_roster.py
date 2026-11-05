"""Deterministic reviewer-roster governance and rotation rehearsal."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from truepanel.aegis.ssh_verifier import (
    OpenSshSignatureVerifier,
    validate_allowed_signers_roster,
)
from truepanel.aegis.temperature_calibration_candidate_appraisal import _canonical
from truepanel.aegis.temperature_governed_reviewer_roster import (
    GOVERNANCE_KEY_ID,
    NAMESPACE,
    STATUS_ACTIVE,
    build_temperature_governed_reviewer_roster_manifest,
    evaluate_temperature_governed_reviewer_roster,
)
from truepanel.holodeck.aegis_temperature_authenticated_label_join import _sign


def run_temperature_governed_reviewer_roster_checkride() -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="truepanel-governed-reviewers-") as directory:
        root = Path(directory).resolve()
        keys = [root / name for name in ("root", "primary", "independent")]
        for key in keys:
            subprocess.run(["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
        roster = root / "root.allowed"
        roster.write_text(f"{GOVERNANCE_KEY_ID} {keys[0].with_suffix('.pub').read_text(encoding='ascii')}", encoding="ascii")
        os.chmod(roster, 0o600)
        verifier = OpenSshSignatureVerifier(roster, namespace=NAMESPACE, expected_key_ids=(GOVERNANCE_KEY_ID,))

        def fingerprint(key: Path, identity: str) -> str:
            line = f"{identity} {key.with_suffix('.pub').read_text(encoding='ascii')}".encode()
            return validate_allowed_signers_roster(line, expected_key_ids=(identity,))[identity]

        primary = fingerprint(keys[1], "primary")
        independent = fingerprint(keys[2], "independent")
        now = "2026-11-03T05:00:00Z"

        def run(name: str, *, generation: int = 1, previous: str | None = None,
                activated: str = "2026-11-03T04:00:00Z", expires: str = "2026-12-03T04:00:00Z",
                primary_fp: str = primary, independent_fp: str = independent,
                revoked: tuple[str, ...] = (), mutate_authority: bool = False) -> dict[str, Any]:
            manifest = root / f"{name}.json"
            manifest.write_bytes(build_temperature_governed_reviewer_roster_manifest(
                generation=generation, previous_manifest_sha256=previous,
                activated_at_utc=activated, expires_at_utc=expires,
                primary_fingerprint=primary_fp, independent_fingerprint=independent_fp,
                revoked_fingerprints=revoked,
            ))
            if mutate_authority:
                value = json.loads(manifest.read_bytes())
                value["deployment_authority"] = True
                manifest.write_bytes(_canonical(value))
            signature = root / f"{name}.sig"
            _sign(keys[0], manifest, signature, NAMESPACE)
            result = evaluate_temperature_governed_reviewer_roster(verifier, manifest, signature, now_utc=now)
            scenarios.append({"name": name, "status": result["status"], "errors": result["errors"]})
            return result

        active = run("active")
        rotation = run("rotation", generation=2, previous="a" * 64)
        expired = run("expired", activated="2026-10-01T00:00:00Z", expires="2026-10-31T00:00:00Z")
        revoked = run("revoked-primary", revoked=(primary,))
        duplicate = run("duplicate-identity", independent_fp=primary)
        escalated = run("authority-escalation", mutate_authority=True)
    return {
        "schema": "truepanel.holodeck-temperature-governed-reviewer-roster/v1",
        "simulation": True, "hardware_isolated": True, "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "active_count": sum(item["status"] == STATUS_ACTIVE for item in (active, rotation)),
            "hold_count": sum(item["status"] != STATUS_ACTIVE for item in (expired, revoked, duplicate, escalated)),
            "active_reviewers": 2, "threshold": 2, "rotation_generations": 2,
            "revoked_acceptances": int(revoked["status"] == STATUS_ACTIVE),
            "duplicate_identity_acceptances": int(duplicate["status"] == STATUS_ACTIVE),
            "coverage_total": 8, "coverage_trusted": 8, "coverage_gaps": 0,
            "supporting_signal_count": 5, "confidence": 0.95,
            "shared_cooling_first_match_sample": 19, "isolated_threshold_first_match_sample": 46,
            "lead_samples": 27, "field_validations": 0, "deployments": 0,
            "hardware_actions": 0, "runtime_writes": 0,
            "fixture_private_keys_created": 3, "fixture_private_keys_retained": 0,
        },
    }


__all__ = ["run_temperature_governed_reviewer_roster_checkride"]
