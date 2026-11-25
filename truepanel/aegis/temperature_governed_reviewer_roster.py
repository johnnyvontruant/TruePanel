"""Root-signed, expiring reviewer roster for temperature replay review."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from .ssh_verifier import MAX_SIGNATURE_BYTES
from .temperature_authenticated_acceptance import KEY_ID
from .temperature_calibration_candidate_appraisal import (
    MAX_PUBLIC_BYTES,
    _canonical,
    _snapshot,
)
from .temperature_two_person_replay_review import REVIEWER_KEY_ID

SCHEMA: Final = "truepanel.aegis-temperature-governed-reviewer-roster/v1"
MANIFEST_SCHEMA: Final = f"{SCHEMA}-manifest"
NAMESPACE: Final = "truepanel-aegis-temperature-reviewer-roster-v1@truepanel"
GOVERNANCE_KEY_ID: Final = "reviewer-roster-governance-root"
STATUS_ACTIVE: Final = "GOVERNED_REVIEWER_ROSTER_ACTIVE"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_GOVERNED_REVIEWER_ROSTER"
STATUS_HOLD: Final = "HOLD"
MAX_VALIDITY: Final = timedelta(days=30)
ROLES: Final = ("primary-replay-reviewer", "independent-replay-reviewer")

_DENIED = (
    "field_validated", "production_validated", "candidate_accepted",
    "candidate_installed", "capture_authority", "runtime_authority",
    "deployment_authority", "hardware_authority", "storage_write_authority",
    "network_authority", "automatic_promotion",
)


def _sha(payload: bytes | Mapping[str, Any]) -> str:
    return hashlib.sha256(payload if isinstance(payload, bytes) else _canonical(payload)).hexdigest()


def _parse(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("ReviewerRosterTimeInvalid")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC:
        raise ValueError("ReviewerRosterTimeInvalid")
    return parsed


def _fingerprint(value: str) -> str:
    if not isinstance(value, str) or not value.startswith("SHA256:") or len(value) < 20:
        raise ValueError("ReviewerRosterFingerprintInvalid")
    return value


def build_temperature_governed_reviewer_roster_manifest(
    *, generation: int, previous_manifest_sha256: str | None,
    activated_at_utc: str, expires_at_utc: str,
    primary_fingerprint: str, independent_fingerprint: str,
    revoked_fingerprints: tuple[str, ...] = (),
) -> bytes:
    start, end = _parse(activated_at_utc), _parse(expires_at_utc)
    if end <= start or end - start > MAX_VALIDITY or not isinstance(generation, int) or generation < 1:
        raise ValueError("ReviewerRosterWindowInvalid")
    if (generation == 1) != (previous_manifest_sha256 is None):
        raise ValueError("ReviewerRosterChainInvalid")
    if generation > 1 and (not isinstance(previous_manifest_sha256, str) or len(previous_manifest_sha256) != 64):
        raise ValueError("ReviewerRosterChainInvalid")
    primary, independent = _fingerprint(primary_fingerprint), _fingerprint(independent_fingerprint)
    revoked = sorted({_fingerprint(item) for item in revoked_fingerprints})
    reviewers = [
        {"role": ROLES[0], "key_id": KEY_ID, "ssh_key_fingerprint": primary, "generation": generation, "status": "ACTIVE", "not_before_utc": activated_at_utc, "not_after_utc": expires_at_utc},
        {"role": ROLES[1], "key_id": REVIEWER_KEY_ID, "ssh_key_fingerprint": independent, "generation": generation, "status": "ACTIVE", "not_before_utc": activated_at_utc, "not_after_utc": expires_at_utc},
    ]
    body: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA, "namespace": NAMESPACE,
        "scope": "reviewer-identity-governance-only", "generation": generation,
        "previous_manifest_sha256": previous_manifest_sha256,
        "activated_at_utc": activated_at_utc, "expires_at_utc": expires_at_utc,
        "reviewers": reviewers, "revoked_fingerprints": revoked,
        "threshold": 2, "distinct_identities_required": True,
        "automatic_rotation": False, **{key: False for key in _DENIED},
    }
    body["manifest_sha256"] = _sha(body)
    return _canonical(body)


def evaluate_temperature_governed_reviewer_roster(
    verifier: Any, manifest_path: str | Path, signature_path: str | Path, *, now_utc: str,
) -> dict[str, Any]:
    errors: list[str] = []
    signature_verified = False
    generation = None
    expires = None
    manifest_digest = None
    try:
        if getattr(verifier, "namespace", None) != NAMESPACE or getattr(verifier, "expected_key_ids", None) != (GOVERNANCE_KEY_ID,):
            raise ValueError("ReviewerRosterVerifierPolicyMismatch")
        payload = _snapshot(Path(manifest_path), MAX_PUBLIC_BYTES)
        manifest = json.loads(payload)
        if not isinstance(manifest, dict):
            raise ValueError("ReviewerRosterManifestInvalid")
        expected = build_temperature_governed_reviewer_roster_manifest(
            generation=manifest["generation"], previous_manifest_sha256=manifest["previous_manifest_sha256"],
            activated_at_utc=manifest["activated_at_utc"], expires_at_utc=manifest["expires_at_utc"],
            primary_fingerprint=manifest["reviewers"][0]["ssh_key_fingerprint"],
            independent_fingerprint=manifest["reviewers"][1]["ssh_key_fingerprint"],
            revoked_fingerprints=tuple(manifest["revoked_fingerprints"]),
        )
        if payload != expected:
            raise ValueError("ReviewerRosterManifestMismatch")
        now = _parse(now_utc)
        if not (_parse(manifest["activated_at_utc"]) <= now < _parse(manifest["expires_at_utc"])):
            raise ValueError("ReviewerRosterNotActive")
        reviewers = manifest["reviewers"]
        if [item["role"] for item in reviewers] != list(ROLES) or [item["key_id"] for item in reviewers] != [KEY_ID, REVIEWER_KEY_ID]:
            raise ValueError("ReviewerRosterRoleMismatch")
        fingerprints = [item["ssh_key_fingerprint"] for item in reviewers]
        if len(set(fingerprints)) != 2:
            raise ValueError("ReviewerRosterIdentityNotDistinct")
        if set(fingerprints) & set(manifest["revoked_fingerprints"]):
            raise ValueError("ReviewerRosterIdentityRevoked")
        signature = _snapshot(Path(signature_path), MAX_SIGNATURE_BYTES)
        signature_verified = verifier(GOVERNANCE_KEY_ID, payload, signature.decode("ascii")) is True
        if not signature_verified:
            raise ValueError("ReviewerRosterSignatureNotAuthenticated")
        generation, expires, manifest_digest = manifest["generation"], manifest["expires_at_utc"], manifest["manifest_sha256"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError, IndexError, OSError, TypeError, UnicodeDecodeError, ValueError) as error:
        errors.append(str(error) or error.__class__.__name__)
    active = not errors
    return {
        "schema": SCHEMA, "status": STATUS_ACTIVE if active else STATUS_HOLD,
        "root_signature_verified": signature_verified, "generation": generation,
        "expires_at_utc": expires, "manifest_sha256": manifest_digest,
        "active_reviewers": 2 if active else 0, "threshold": 2,
        "distinct_identities_verified": active, "revocation_checked": active,
        "reviewer_quorum_authorized": active,
        **{key: False for key in _DENIED}, "errors": errors,
    }


def pending_temperature_governed_reviewer_roster(two_person: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": STATUS_REQUIRED if two_person.get("primary_review_present") is True else STATUS_HOLD,
        "root_signature_verified": False, "generation": None, "expires_at_utc": None,
        "active_reviewers": 0, "threshold": 2, "distinct_identities_verified": False,
        "revocation_checked": False, "reviewer_quorum_authorized": False,
        **{key: False for key in _DENIED},
        "next_action": "Provision a root-signed, unexpired two-role reviewer roster; rehearse rotation and revocation before trusting quorum.",
    }


__all__ = ["GOVERNANCE_KEY_ID", "NAMESPACE", "SCHEMA", "STATUS_ACTIVE", "STATUS_HOLD", "build_temperature_governed_reviewer_roster_manifest", "evaluate_temperature_governed_reviewer_roster", "pending_temperature_governed_reviewer_roster"]
