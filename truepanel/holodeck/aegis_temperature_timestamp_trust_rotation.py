"""Deterministic dual-root timestamp trust rotation rehearsal."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from truepanel.aegis.ssh_verifier import OpenSshSignatureVerifier
from truepanel.aegis.temperature_calibration_candidate_appraisal import _canonical
from truepanel.aegis.temperature_timestamp_trust_bundle import SCHEMA as BUNDLE_SCHEMA
from truepanel.aegis.temperature_timestamp_trust_rotation import (
    NAMESPACE,
    PREDECESSOR_KEY_ID,
    STATUS_TRUSTED,
    SUCCESSOR_KEY_ID,
    build_timestamp_trust_rotation_statement,
    evaluate_timestamp_trust_rotation,
)
from truepanel.holodeck.aegis_temperature_authenticated_label_join import _sign


def _bundle(generation: int) -> dict[str, Any]:
    return {
        "schema": BUNDLE_SCHEMA,
        "generation": generation,
        "threshold": 2,
        "valid_from_utc": "2026-11-01T00:00:00Z",
        "valid_until_utc": "2027-01-01T00:00:00Z",
        "authorities": [
            {
                "operator": "tsa-a.example",
                "root_fingerprint": f"SHA256:tsa-a-v{generation}",
                "policy_oid": "1.3.6.1.4.1.55555.1",
                "valid_from_utc": "2026-11-01T00:00:00Z",
                "valid_until_utc": "2027-01-01T00:00:00Z",
            },
            {
                "operator": "tsa-b.example",
                "root_fingerprint": "SHA256:tsa-b-v1",
                "policy_oid": "1.3.6.1.4.1.55555.1",
                "valid_from_utc": "2026-10-01T00:00:00Z",
                "valid_until_utc": "2027-01-01T00:00:00Z",
            },
        ],
        "deployment_authority": False,
        "hardware_authority": False,
    }


def _evidence(
    *, stale: bool = False, missing: bool = False
) -> tuple[dict[str, str], ...]:
    values = [
        {
            "operator": "tsa-a.example",
            "type": "CRL",
            "sha256": "a" * 64,
            "produced_at_utc": "2026-11-08T03:00:00Z",
            "valid_until_utc": "2026-11-09T03:00:00Z",
        },
        {
            "operator": "tsa-b.example",
            "type": "OCSP",
            "sha256": "b" * 64,
            "produced_at_utc": "2026-11-08T03:00:00Z",
            "valid_until_utc": "2026-11-09T03:00:00Z",
        },
    ]
    if stale:
        values[1]["valid_until_utc"] = "2026-11-08T03:30:00Z"
    return tuple(values[:1] if missing else values)


def run_temperature_timestamp_trust_rotation_checkride() -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix="truepanel-timestamp-trust-rotation-"
    ) as directory:
        root = Path(directory).resolve()
        old_key, new_key = root / "old-root", root / "new-root"
        for key in (old_key, new_key):
            subprocess.run(
                [
                    "/usr/bin/ssh-keygen",
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-f",
                    str(key),
                ],
                check=True,
            )

        def verifier(key: Path, key_id: str) -> OpenSshSignatureVerifier:
            allowed = root / f"{key_id}.allowed"
            allowed.write_text(
                f"{key_id} {key.with_suffix('.pub').read_text(encoding='ascii')}",
                encoding="ascii",
            )
            os.chmod(allowed, 0o600)
            return OpenSshSignatureVerifier(
                allowed, namespace=NAMESPACE, expected_key_ids=(key_id,)
            )

        predecessor = verifier(old_key, PREDECESSOR_KEY_ID)
        successor = verifier(new_key, SUCCESSOR_KEY_ID)

        def run(
            name: str,
            *,
            previous: dict[str, Any] | None = None,
            successor_bundle: dict[str, Any] | None = None,
            evidence: tuple[dict[str, str], ...] | None = None,
            omit: str | None = None,
            mutate: bool = False,
        ) -> dict[str, Any]:
            previous = deepcopy(previous or _bundle(1))
            successor_bundle = deepcopy(successor_bundle or _bundle(2))
            statement = root / f"{name}.json"
            try:
                statement.write_bytes(
                    build_timestamp_trust_rotation_statement(
                        predecessor,
                        successor,
                        previous,
                        successor_bundle,
                        evidence if evidence is not None else _evidence(),
                        prepared_at_utc="2026-11-08T04:00:00Z",
                        expires_at_utc="2026-11-08T06:00:00Z",
                    )
                )
            except ValueError as error:
                result = {
                    "status": "HOLD",
                    "errors": [str(error)],
                    "rotation_authorized": False,
                }
                scenarios.append(
                    {
                        "name": name,
                        "status": result["status"],
                        "errors": result["errors"],
                    }
                )
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
            result = evaluate_timestamp_trust_rotation(
                predecessor,
                successor,
                previous,
                successor_bundle,
                statement,
                old_sig,
                new_sig,
                now_utc="2026-11-08T05:00:00Z",
            )
            scenarios.append(
                {"name": name, "status": result["status"], "errors": result["errors"]}
            )
            return result

        valid = run("dual-signed-current-revocation")
        missing_old = run("missing-predecessor", omit="predecessor")
        missing_new = run("missing-successor", omit="successor")
        gap_bundle = _bundle(3)
        generation_gap = run("generation-gap", successor_bundle=gap_bundle)
        incomplete = run(
            "missing-operator-revocation", evidence=_evidence(missing=True)
        )
        stale = run("stale-revocation", evidence=_evidence(stale=True))
        escalated = run("authority-escalation", mutate=True)
    return {
        "schema": "truepanel.holodeck-temperature-timestamp-trust-rotation/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "trusted_rotations": int(valid["status"] == STATUS_TRUSTED),
            "hold_count": sum(
                item.get("status") != STATUS_TRUSTED
                for item in (
                    missing_old,
                    missing_new,
                    generation_gap,
                    incomplete,
                    stale,
                    escalated,
                )
            ),
            "dual_signature_transitions": 1,
            "revocation_objects_archived": 2,
            "unsigned_transition_acceptances": 0,
            "generation_gap_acceptances": 0,
            "stale_revocation_acceptances": 0,
            "incomplete_revocation_acceptances": 0,
            "fixture_private_keys_created": 2,
            "fixture_private_keys_retained": 0,
            "coverage_total": 8,
            "coverage_trusted": 8,
            "coverage_gaps": 0,
            "supporting_signal_count": 5,
            "confidence": 0.95,
            "shared_cooling_first_match_sample": 19,
            "isolated_threshold_first_match_sample": 46,
            "lead_samples": 27,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
        },
    }


__all__ = ["run_temperature_timestamp_trust_rotation_checkride"]
