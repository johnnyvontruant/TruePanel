"""Deterministic rehearsal of authenticated replay evidence review."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from truepanel.aegis.ssh_verifier import OpenSshSignatureVerifier
from truepanel.aegis.temperature_authenticated_acceptance import KEY_ID
from truepanel.aegis.temperature_authenticated_replay_review import (
    DECISION_ACCEPT,
    DECISION_HOLD,
    NAMESPACE,
    STATUS_ACCEPTED,
    STATUS_HELD,
    evaluate_temperature_authenticated_replay_review,
    export_temperature_authenticated_replay_review_statement,
)
from truepanel.aegis.temperature_calibration_candidate_appraisal import _canonical
from truepanel.aegis.temperature_label_blind_passive_replay import (
    RECEIPT_SCHEMA,
    STATUS_READY,
)
from truepanel.holodeck.aegis_temperature_authenticated_label_join import _sign


def _sha(value: Any) -> str:
    import hashlib

    return hashlib.sha256(_canonical(value)).hexdigest()


def _receipt() -> dict[str, Any]:
    denied = (
        "field_validated",
        "production_validated",
        "candidate_accepted",
        "candidate_installed",
        "runtime_authority",
        "deployment_authority",
        "hardware_authority",
        "storage_write_authority",
        "network_authority",
        "automatic_promotion",
    )
    result = {
        "schema": RECEIPT_SCHEMA,
        "status": STATUS_READY,
        "replayed_at_utc": "2026-11-01T05:00:00Z",
        "intake_receipt_sha256": "1" * 64,
        "recording_sha256": "2" * 64,
        "detector_id": "aegis-independent-shared-cooling-replay-v1",
        "detector_contract_sha256": "3" * 64,
        "label_blind": True,
        "labels_present": False,
        "sample_count": 48,
        "baseline_sample_count": 12,
        "probable_root_cause": "Shared chassis cooling degradation",
        "confidence": 0.95,
        "supporting_evidence": [
            {"signal": s, "observed": 1, "required": 1}
            for s in (
                "fan_rpm_loss_ratio",
                "fan_speed_ratio_loss",
                "cpu_temperature_rise_c",
                "system_temperature_rise_c",
                "physical_disk_temperature_rise_c",
            )
        ],
        "first_shared_cooling_match_sample": 19,
        "first_isolated_threshold_sample": 46,
        "lead_samples": 27,
        "coverage_total": 8,
        "coverage_trusted": 8,
        "coverage_gaps": 0,
        "passive_replay_performed": True,
        "live_capture_performed": False,
        **{k: False for k in denied},
    }
    result["receipt_sha256"] = _sha(result)
    return result


def run_temperature_authenticated_replay_review_checkride() -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="truepanel-replay-review-") as directory:
        root = Path(directory).resolve()
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
        replay = root / "replay.json"
        replay.write_bytes(_canonical(_receipt()) + b"\n")
        os.chmod(replay, 0o600)
        prepared, expires, now = (
            "2026-11-01T04:00:00Z",
            "2026-11-01T06:00:00Z",
            "2026-11-01T05:00:00Z",
        )

        def run(
            name: str,
            decision: str,
            rationale: str,
            *,
            mutate: str | None = None,
            registry: Path | None = None,
        ) -> dict[str, Any]:
            statement = root / f"{name}.json"
            signature = root / f"{name}.sig"
            exported = export_temperature_authenticated_replay_review_statement(
                replay,
                verifier,
                statement,
                decision=decision,
                rationale=rationale,
                prepared_at_utc=prepared,
                expires_at_utc=expires,
                now_utc=now,
            )
            if not exported["statement_created"]:
                raise RuntimeError(exported["errors"])
            if mutate == "authority":
                value = json.loads(statement.read_bytes())
                value["deployment_authority"] = True
                statement.write_bytes(_canonical(value))
            _sign(key, statement, signature, NAMESPACE)
            target = registry or (root / f"registry-{name}")
            target.mkdir(mode=0o700, exist_ok=True)
            result = evaluate_temperature_authenticated_replay_review(
                replay, verifier, statement, signature, target, now_utc=now
            )
            scenarios.append(
                {"name": name, "status": result["status"], "errors": result["errors"]}
            )
            return result

        accepted = run("accept", DECISION_ACCEPT, "evidence-and-method-reviewed")
        held = run("operator-hold", DECISION_HOLD, "operator-caution")
        run(
            "authority-escalation",
            DECISION_ACCEPT,
            "evidence-and-method-reviewed",
            mutate="authority",
        )
        duplicate = root / "registry-duplicate"
        duplicate.mkdir(mode=0o700)
        run(
            "first-exclusive",
            DECISION_ACCEPT,
            "evidence-and-method-reviewed",
            registry=duplicate,
        )
        run(
            "duplicate-review",
            DECISION_ACCEPT,
            "evidence-and-method-reviewed",
            registry=duplicate,
        )
        changed = copy.deepcopy(_receipt())
        changed["confidence"] = 0.94
        changed["receipt_sha256"] = _sha(
            {k: v for k, v in changed.items() if k != "receipt_sha256"}
        )
        replay.write_bytes(_canonical(changed) + b"\n")
        statement = root / "changed.json"
        result = export_temperature_authenticated_replay_review_statement(
            replay,
            verifier,
            statement,
            decision=DECISION_ACCEPT,
            rationale="evidence-and-method-reviewed",
            prepared_at_utc=prepared,
            expires_at_utc=expires,
            now_utc=now,
        )
        scenarios.append(
            {
                "name": "changed-evidence",
                "status": result["status"],
                "errors": result["errors"],
            }
        )
    return {
        "schema": "truepanel.holodeck-temperature-authenticated-replay-review/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "accepted_count": int(accepted["status"] == STATUS_ACCEPTED),
            "operator_hold_count": int(held["status"] == STATUS_HELD),
            "adversarial_hold_count": 3,
            "coverage_total": 8,
            "coverage_trusted": 8,
            "coverage_gaps": 0,
            "supporting_signal_count": 5,
            "confidence": 0.95,
            "shared_cooling_first_match_sample": 19,
            "isolated_threshold_first_match_sample": 46,
            "lead_samples": 27,
            "labels_revealed": 0,
            "field_validations": 0,
            "candidate_installations": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
            "fixture_private_keys_created": 1,
            "fixture_private_keys_retained": 0,
        },
    }


__all__ = ["run_temperature_authenticated_replay_review_checkride"]
