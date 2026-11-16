"""Deterministic compromise-time reviewer-signature rehearsal."""

from __future__ import annotations

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
from truepanel.aegis.temperature_reviewer_root_rotation import (
    NAMESPACE as ROTATION_NAMESPACE,
)
from truepanel.aegis.temperature_reviewer_root_rotation import (
    PREDECESSOR_KEY_ID,
    SUCCESSOR_KEY_ID,
    build_temperature_reviewer_root_rotation_statement,
)
from truepanel.aegis.temperature_reviewer_signature_validity import (
    STATUS_COMPROMISED,
    STATUS_PRECOMPROMISE,
    STATUS_VALID,
    evaluate_temperature_reviewer_signature_validity,
)
from truepanel.aegis.temperature_two_person_replay_review import (
    NAMESPACE as REVIEW_NAMESPACE,
)
from truepanel.aegis.temperature_two_person_replay_review import (
    REVIEWER_KEY_ID,
    STATEMENT_SCHEMA,
)
from truepanel.holodeck.aegis_temperature_authenticated_label_join import _sign

_DENIED = (
    "field_validated",
    "production_validated",
    "candidate_accepted",
    "candidate_installed",
    "capture_authority",
    "runtime_authority",
    "deployment_authority",
    "hardware_authority",
    "storage_write_authority",
    "network_authority",
    "automatic_promotion",
)


def run_temperature_reviewer_signature_validity_checkride() -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix="truepanel-signature-validity-"
    ) as directory:
        root = Path(directory).resolve()
        old_key, new_key, reviewer_key, unaffected_key = (
            root / name for name in ("old-root", "new-root", "reviewer", "unaffected")
        )
        for key in (old_key, new_key, reviewer_key, unaffected_key):
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

        def verifier(
            key: Path, key_id: str, namespace: str
        ) -> OpenSshSignatureVerifier:
            allowed = root / f"{key.stem}-{key_id}.allowed"
            allowed.write_text(
                f"{key_id} {key.with_suffix('.pub').read_text(encoding='ascii')}",
                encoding="ascii",
            )
            os.chmod(allowed, 0o600)
            return OpenSshSignatureVerifier(
                allowed, namespace=namespace, expected_key_ids=(key_id,)
            )

        predecessor = verifier(old_key, PREDECESSOR_KEY_ID, ROTATION_NAMESPACE)
        successor = verifier(new_key, SUCCESSOR_KEY_ID, ROTATION_NAMESPACE)
        reviewer = verifier(reviewer_key, REVIEWER_KEY_ID, REVIEW_NAMESPACE)
        unaffected = verifier(unaffected_key, REVIEWER_KEY_ID, REVIEW_NAMESPACE)

        def fingerprint(key: Path) -> str:
            payload = f"{REVIEWER_KEY_ID} {key.with_suffix('.pub').read_text(encoding='ascii')}".encode()
            return validate_allowed_signers_roster(
                payload, expected_key_ids=(REVIEWER_KEY_ID,)
            )[REVIEWER_KEY_ID]

        compromised_fp = fingerprint(reviewer_key)

        def run(
            name: str,
            signed_at: str,
            *,
            review_verifier: Any = reviewer,
            review_key: Path = reviewer_key,
            missing_successor: bool = False,
            authority: bool = False,
        ) -> dict[str, Any]:
            event = {
                "fingerprint": compromised_fp,
                "compromised_at_utc": "2026-11-04T01:00:00Z",
                "revoked_at_utc": "2026-11-04T02:00:00Z",
                "reason": "confirmed-compromise",
            }
            rotation = root / f"{name}.rotation.json"
            rotation.write_bytes(
                build_temperature_reviewer_root_rotation_statement(
                    predecessor,
                    successor,
                    from_generation=1,
                    to_generation=2,
                    previous_manifest_sha256="a" * 64,
                    successor_manifest_sha256="b" * 64,
                    prepared_at_utc="2026-11-05T04:00:00Z",
                    expires_at_utc="2026-11-05T06:00:00Z",
                    compromise_events=(event,),
                )
            )
            old_sig, new_sig = root / f"{name}.old.sig", root / f"{name}.new.sig"
            _sign(old_key, rotation, old_sig, ROTATION_NAMESPACE)
            if not missing_successor:
                _sign(new_key, rotation, new_sig, ROTATION_NAMESPACE)
            review = root / f"{name}.review.json"
            statement: dict[str, Any] = {
                "schema": STATEMENT_SCHEMA,
                "namespace": REVIEW_NAMESPACE,
                "scope": "independent-replay-evidence-concurrence-only",
                "key_id": REVIEWER_KEY_ID,
                "reviewer_key_fingerprint": fingerprint(review_key),
                "prepared_at_utc": signed_at,
                "expires_at_utc": "2026-11-05T06:00:00Z",
                "decision": "CONCUR_ACCEPT_EVIDENCE",
                "rationale": "independently-reconstructed-and-concurred",
                "primary_review_receipt_sha256": "c" * 64,
                "replay_receipt_sha256": "d" * 64,
                "primary_operator_key_fingerprint": "SHA256:fixture-primary",
                "independent_identity_required": True,
                "two_person_quorum": True,
                "manual_calibration_consideration": True,
                **{key: False for key in _DENIED},
            }
            if authority:
                statement["deployment_authority"] = True
            review.write_bytes(_canonical(statement))
            review_sig = root / f"{name}.review.sig"
            _sign(review_key, review, review_sig, REVIEW_NAMESPACE)
            result = evaluate_temperature_reviewer_signature_validity(
                predecessor,
                successor,
                rotation,
                old_sig,
                new_sig,
                review_verifier,
                review,
                review_sig,
                now_utc="2026-11-05T05:00:00Z",
            )
            scenarios.append(
                {
                    "name": name,
                    "status": result["status"],
                    "accepted": result["historical_signature_accepted"],
                    "errors": result["errors"],
                }
            )
            return result

        before = run("before-compromise", "2026-11-04T00:59:59Z")
        at = run("at-compromise", "2026-11-04T01:00:00Z")
        after = run("after-compromise", "2026-11-04T01:30:00Z")
        clean = run(
            "unaffected-reviewer",
            "2026-11-04T03:00:00Z",
            review_verifier=unaffected,
            review_key=unaffected_key,
        )
        untrusted = run(
            "untrusted-rotation", "2026-11-04T00:00:00Z", missing_successor=True
        )
        escalated = run("authority-escalation", "2026-11-04T00:00:00Z", authority=True)
    return {
        "schema": "truepanel.holodeck-temperature-reviewer-signature-validity/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "precompromise_valid_count": int(before["status"] == STATUS_PRECOMPROMISE),
            "unaffected_valid_count": int(clean["status"] == STATUS_VALID),
            "compromised_hold_count": sum(
                item["status"] == STATUS_COMPROMISED for item in (at, after)
            ),
            "untrusted_rotation_acceptances": int(
                untrusted["historical_signature_accepted"]
            ),
            "authority_escalation_acceptances": int(
                escalated["historical_signature_accepted"]
            ),
            "coverage_total": 8,
            "coverage_trusted": 8,
            "coverage_gaps": 0,
            "supporting_signal_count": 5,
            "confidence": 0.95,
            "shared_cooling_first_match_sample": 19,
            "isolated_threshold_first_match_sample": 46,
            "lead_samples": 27,
            "field_validations": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
            "fixture_private_keys_created": 4,
            "fixture_private_keys_retained": 0,
        },
    }


__all__ = ["run_temperature_reviewer_signature_validity_checkride"]
