"""Dual-root reviewer-governance rotation receipt."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from .ssh_verifier import (
    MAX_ALLOWED_SIGNERS_BYTES,
    MAX_SIGNATURE_BYTES,
    validate_allowed_signers_roster,
)
from .temperature_calibration_candidate_appraisal import (
    MAX_PUBLIC_BYTES,
    _canonical,
    _snapshot,
)

SCHEMA: Final = "truepanel.aegis-temperature-reviewer-root-rotation/v1"
STATEMENT_SCHEMA: Final = f"{SCHEMA}-statement"
NAMESPACE: Final = "truepanel-aegis-reviewer-root-rotation-v1@truepanel"
PREDECESSOR_KEY_ID: Final = "reviewer-governance-root-predecessor"
SUCCESSOR_KEY_ID: Final = "reviewer-governance-root-successor"
STATUS_TRUSTED: Final = "DUAL_ROOT_ROTATION_TRUSTED"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_DUAL_ROOT_ROTATION"
STATUS_HOLD: Final = "HOLD"
MAX_WINDOW: Final = timedelta(hours=2)
_DENIED = ("field_validated", "production_validated", "candidate_accepted", "candidate_installed", "capture_authority", "runtime_authority", "deployment_authority", "hardware_authority", "storage_write_authority", "network_authority", "automatic_promotion")


def _sha(value: bytes | Mapping[str, Any]) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else _canonical(value)).hexdigest()


def _time(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("RootRotationTimeInvalid")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC:
        raise ValueError("RootRotationTimeInvalid")
    return parsed


def _root_fingerprint(verifier: Any, key_id: str) -> str:
    if getattr(verifier, "namespace", None) != NAMESPACE or getattr(verifier, "expected_key_ids", None) != (key_id,):
        raise ValueError("RootRotationVerifierPolicyMismatch")
    path = getattr(verifier, "allowed_signers_path", None)
    if not isinstance(path, Path):
        raise ValueError("RootRotationVerifierPolicyMismatch")
    return validate_allowed_signers_roster(_snapshot(path, MAX_ALLOWED_SIGNERS_BYTES), expected_key_ids=(key_id,))[key_id]


def build_temperature_reviewer_root_rotation_statement(
    predecessor_verifier: Any, successor_verifier: Any, *,
    from_generation: int, to_generation: int,
    previous_manifest_sha256: str, successor_manifest_sha256: str,
    prepared_at_utc: str, expires_at_utc: str,
    compromise_events: tuple[Mapping[str, str], ...] = (),
) -> bytes:
    start, end = _time(prepared_at_utc), _time(expires_at_utc)
    if end <= start or end - start > MAX_WINDOW:
        raise ValueError("RootRotationWindowInvalid")
    if not isinstance(from_generation, int) or to_generation != from_generation + 1 or from_generation < 1:
        raise ValueError("RootRotationGenerationInvalid")
    if any(not isinstance(value, str) or len(value) != 64 for value in (previous_manifest_sha256, successor_manifest_sha256)):
        raise ValueError("RootRotationManifestDigestInvalid")
    predecessor = _root_fingerprint(predecessor_verifier, PREDECESSOR_KEY_ID)
    successor = _root_fingerprint(successor_verifier, SUCCESSOR_KEY_ID)
    if predecessor == successor:
        raise ValueError("RootRotationIdentityNotDistinct")
    events = []
    for event in compromise_events:
        if set(event) != {"fingerprint", "compromised_at_utc", "revoked_at_utc", "reason"}:
            raise ValueError("RootRotationCompromiseEventInvalid")
        compromised, revoked = _time(event["compromised_at_utc"]), _time(event["revoked_at_utc"])
        if compromised > revoked or revoked > start or event["reason"] not in {"suspected-compromise", "confirmed-compromise", "scheduled-retirement"}:
            raise ValueError("RootRotationCompromiseTimelineInvalid")
        events.append(dict(event))
    body: dict[str, Any] = {
        "schema": STATEMENT_SCHEMA, "namespace": NAMESPACE,
        "scope": "reviewer-governance-root-rotation-only",
        "from_generation": from_generation, "to_generation": to_generation,
        "previous_manifest_sha256": previous_manifest_sha256,
        "successor_manifest_sha256": successor_manifest_sha256,
        "predecessor_root_fingerprint": predecessor,
        "successor_root_fingerprint": successor,
        "prepared_at_utc": prepared_at_utc, "expires_at_utc": expires_at_utc,
        "compromise_events": events, "predecessor_signature_required": True,
        "successor_signature_required": True, "automatic_rotation": False,
        **{key: False for key in _DENIED},
    }
    body["statement_sha256"] = _sha(body)
    return _canonical(body)


def evaluate_temperature_reviewer_root_rotation(
    predecessor_verifier: Any, successor_verifier: Any,
    statement_path: str | Path, predecessor_signature_path: str | Path,
    successor_signature_path: str | Path, *, now_utc: str,
) -> dict[str, Any]:
    errors: list[str] = []
    predecessor_verified = successor_verified = False
    generation = None
    events = 0
    try:
        payload = _snapshot(Path(statement_path), MAX_PUBLIC_BYTES)
        statement = json.loads(payload)
        expected = build_temperature_reviewer_root_rotation_statement(
            predecessor_verifier, successor_verifier,
            from_generation=statement["from_generation"], to_generation=statement["to_generation"],
            previous_manifest_sha256=statement["previous_manifest_sha256"], successor_manifest_sha256=statement["successor_manifest_sha256"],
            prepared_at_utc=statement["prepared_at_utc"], expires_at_utc=statement["expires_at_utc"],
            compromise_events=tuple(statement["compromise_events"]),
        )
        if payload != expected:
            raise ValueError("RootRotationStatementMismatch")
        if not (_time(statement["prepared_at_utc"]) <= _time(now_utc) < _time(statement["expires_at_utc"])):
            raise ValueError("RootRotationNotActive")
        if not Path(predecessor_signature_path).exists() or not Path(successor_signature_path).exists():
            raise ValueError("RootRotationDualSignatureRequired")
        predecessor_signature = _snapshot(Path(predecessor_signature_path), MAX_SIGNATURE_BYTES).decode("ascii")
        successor_signature = _snapshot(Path(successor_signature_path), MAX_SIGNATURE_BYTES).decode("ascii")
        predecessor_verified = predecessor_verifier(PREDECESSOR_KEY_ID, payload, predecessor_signature) is True
        successor_verified = successor_verifier(SUCCESSOR_KEY_ID, payload, successor_signature) is True
        if not predecessor_verified or not successor_verified:
            raise ValueError("RootRotationDualSignatureRequired")
        generation, events = statement["to_generation"], len(statement["compromise_events"])
    except (FileNotFoundError, json.JSONDecodeError, KeyError, OSError, TypeError, UnicodeDecodeError, ValueError) as error:
        errors.append(str(error) or error.__class__.__name__)
    trusted = not errors
    return {"schema": SCHEMA, "status": STATUS_TRUSTED if trusted else STATUS_HOLD,
            "predecessor_signature_verified": predecessor_verified,
            "successor_signature_verified": successor_verified,
            "dual_control_verified": trusted, "to_generation": generation,
            "compromise_events_verified": events, "rotation_authorized": trusted,
            **{key: False for key in _DENIED}, "errors": errors}


def pending_temperature_reviewer_root_rotation(roster: Mapping[str, Any]) -> dict[str, Any]:
    return {"schema": SCHEMA, "status": STATUS_REQUIRED if roster.get("status") == "GOVERNED_REVIEWER_ROSTER_ACTIVE" else STATUS_HOLD,
            "predecessor_signature_verified": False, "successor_signature_verified": False,
            "dual_control_verified": False, "to_generation": None,
            "compromise_events_verified": 0, "rotation_authorized": False,
            **{key: False for key in _DENIED},
            "next_action": "Rehearse a predecessor-and-successor signed root transition with explicit compromise timestamps before provisioning human reviewer keys."}


__all__ = ["NAMESPACE", "PREDECESSOR_KEY_ID", "SUCCESSOR_KEY_ID", "STATUS_TRUSTED", "build_temperature_reviewer_root_rotation_statement", "evaluate_temperature_reviewer_root_rotation", "pending_temperature_reviewer_root_rotation"]
