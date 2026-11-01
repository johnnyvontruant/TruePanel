"""Digest-bound, provider-neutral recovery evidence for Project AEGIS.

The statement shape adapts the subject/digest/predicate separation used by
in-toto attestations, but it is intentionally a TruePanel-owned contract.
Digests detect mutation; they do not authenticate a provider.  Provider trust,
freshness, incident binding, and semantic claims are validated separately.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

SCHEMA_TYPE = "https://truepanel.dev/attestation/recovery/v1"
BACKUP_KIND = "backup.restore-verification"
CANDIDATE_KIND = "storage.replacement-candidate"
KNOWN_KINDS = (BACKUP_KIND, CANDIDATE_KIND)
KNOWN_PROVIDER_MODES = {
    "deterministic_fixture",
    "passive_local",
    "external_verifier",
}
DEFAULT_TTL_SECONDS = 15 * 60


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _timestamp(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = _text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _is_sha256(value: Any) -> bool:
    text = _text(value).lower()
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def issue_recovery_attestation(
    *,
    kind: str,
    incident_id: str,
    provider_id: str,
    provider_mode: str,
    observed_at: Any,
    subject_name: str,
    subject_sha256: str,
    claims: dict[str, Any],
    evidence_reference: str,
    evidence_maturity: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, Any]:
    """Issue a deterministic advisory statement without granting authority."""

    observed = _timestamp(observed_at)
    expires_at = observed + ttl_seconds if observed is not None else None
    statement = {
        "_type": SCHEMA_TYPE,
        "schema_version": 1,
        "kind": _text(kind),
        "incident_id": _text(incident_id),
        "subject": [
            {
                "name": _text(subject_name),
                "digest": {"sha256": _text(subject_sha256).lower()},
            }
        ],
        "predicate": {
            "provider": {
                "id": _text(provider_id),
                "mode": _text(provider_mode),
                "evidence_reference": _text(evidence_reference),
            },
            "observed_at": observed_at,
            "expires_at": expires_at,
            "ttl_seconds": ttl_seconds,
            "evidence_maturity": _text(evidence_maturity),
            "claims": claims,
            "read_only": True,
            "control_authority": False,
            "cryptographic_authenticity": False,
            "integrity_disclosure": (
                "SHA-256 detects statement mutation; it does not authenticate "
                "the evidence provider."
            ),
        },
    }
    statement["statement_sha256"] = _digest(statement)
    return statement


def validate_recovery_attestation(
    statement: dict[str, Any],
    *,
    incident_id: str,
    now: Any,
) -> tuple[str, ...]:
    """Validate shape, integrity, scope, authority, and freshness."""

    errors: list[str] = []
    if statement.get("_type") != SCHEMA_TYPE:
        errors.append("unsupported attestation schema")
    if statement.get("kind") not in KNOWN_KINDS:
        errors.append("unsupported attestation kind")
    if _text(statement.get("incident_id")) != _text(incident_id):
        errors.append("incident binding mismatch")

    subjects = _list(statement.get("subject"))
    if len(subjects) != 1:
        errors.append("exactly one digested subject is required")
    else:
        subject = _dict(subjects[0])
        if not _text(subject.get("name")):
            errors.append("subject name is missing")
        if not _is_sha256(_dict(subject.get("digest")).get("sha256")):
            errors.append("subject SHA-256 is missing or invalid")

    predicate = _dict(statement.get("predicate"))
    provider = _dict(predicate.get("provider"))
    if not _text(provider.get("id")):
        errors.append("provider identity is missing")
    if provider.get("mode") not in KNOWN_PROVIDER_MODES:
        errors.append("provider mode is not governed")
    if not _text(provider.get("evidence_reference")):
        errors.append("provider evidence reference is missing")
    if predicate.get("read_only") is not True:
        errors.append("attestation is not read-only")
    if predicate.get("control_authority") is not False:
        errors.append("attestation grants control authority")
    if predicate.get("cryptographic_authenticity") is not False:
        errors.append("digest must not be presented as provider authentication")
    if not _text(predicate.get("evidence_maturity")):
        errors.append("evidence maturity is missing")

    observed = _timestamp(predicate.get("observed_at"))
    expires = _timestamp(predicate.get("expires_at"))
    current = _timestamp(now)
    if observed is None or expires is None or current is None:
        errors.append("attestation freshness cannot be established")
    else:
        if observed > current + 5:
            errors.append("attestation observation is in the future")
        if current > expires:
            errors.append("attestation has expired")
        if expires <= observed:
            errors.append("attestation expiry is not after observation")

    expected = _text(statement.get("statement_sha256")).lower()
    unsigned = dict(statement)
    unsigned.pop("statement_sha256", None)
    if not _is_sha256(expected) or _digest(unsigned) != expected:
        errors.append("attestation digest mismatch")
    return tuple(errors)


def _selected_candidate(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    sessions = _list(_dict(payload.get("lifeline")).get("sessions"))
    for session in sessions:
        if not isinstance(session, dict) or session.get("status") != "active":
            continue
        context = _dict(session.get("context"))
        candidates = [
            item
            for item in _list(context.get("replacement_candidates"))
            if isinstance(item, dict)
        ]
        selected = [item for item in candidates if item.get("selected") is True]
        candidate = selected[0] if len(selected) == 1 else (
            candidates[0] if len(candidates) == 1 else {}
        )
        if candidate:
            return session, candidate
    return {}, {}


def collect_recovery_attestations(
    payload: dict[str, Any],
    *,
    incident_id: str,
    source_identity_sha256: str | None,
) -> list[dict[str, Any]]:
    """Adapt governed payload evidence behind a replaceable provider boundary."""

    statements: list[dict[str, Any]] = []
    backup = _dict(payload.get("backup_context"))
    backup_subject = _text(backup.get("evidence_sha256"))
    if backup:
        statements.append(
            issue_recovery_attestation(
                kind=BACKUP_KIND,
                incident_id=incident_id,
                provider_id=_text(backup.get("provider_id")),
                provider_mode=_text(backup.get("provider_mode")),
                observed_at=backup.get("verified_at"),
                subject_name=_text(backup.get("scope")) or "backup-restore-evidence",
                subject_sha256=backup_subject,
                evidence_reference=_text(backup.get("evidence_reference")),
                evidence_maturity=_text(backup.get("evidence_maturity")),
                claims={
                    "independent_backup_confirmed": (
                        backup.get("independent_backup_confirmed") is True
                    ),
                    "restore_tested": backup.get("restore_tested") is True,
                    "restore_test_id": _text(backup.get("restore_test_id")),
                    "scope": _text(backup.get("scope")),
                },
            )
        )

    session, candidate = _selected_candidate(payload)
    if candidate:
        replacement = _dict(_dict(session.get("last_session")).get("replacement"))
        candidate_digest = _text(candidate.get("identity_sha256"))
        statements.append(
            issue_recovery_attestation(
                kind=CANDIDATE_KIND,
                incident_id=incident_id,
                provider_id=_text(candidate.get("provider_id")),
                provider_mode=_text(candidate.get("provider_mode")),
                observed_at=candidate.get("observed_at", session.get("updated_at")),
                subject_name=_text(candidate.get("model")) or "replacement-candidate",
                subject_sha256=candidate_digest,
                evidence_reference=_text(candidate.get("evidence_reference")),
                evidence_maturity=_text(candidate.get("evidence_maturity")),
                claims={
                    "validation_passed": replacement.get("valid") is True,
                    "identity_verified_distinct": bool(
                        _is_sha256(source_identity_sha256)
                        and _is_sha256(candidate_digest)
                        and candidate_digest.lower()
                        != _text(source_identity_sha256).lower()
                    ),
                    "member_of_pool": candidate.get("member_of_pool"),
                    "contains_preserved_data": candidate.get("contains_preserved_data"),
                    "capacity_bytes": candidate.get("capacity_bytes"),
                    "minimum_capacity_bytes": replacement.get(
                        "minimum_capacity_bytes"
                    ),
                },
            )
        )
    return statements


def reconcile_recovery_attestations(
    statements: list[dict[str, Any]],
    *,
    incident_id: str,
    now: Any,
) -> dict[str, Any]:
    """Reconcile attestations and fail closed on gaps or contradictions."""

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for statement in statements:
        errors = list(
            validate_recovery_attestation(
                statement,
                incident_id=incident_id,
                now=now,
            )
        )
        claims = _dict(_dict(statement.get("predicate")).get("claims"))
        kind = statement.get("kind")
        if kind == BACKUP_KIND:
            if claims.get("independent_backup_confirmed") is not True:
                errors.append("backup is not independently confirmed")
            if claims.get("restore_tested") is not True:
                errors.append("restore test has not passed")
            if not _text(claims.get("restore_test_id")):
                errors.append("restore test identity is missing")
            if not _text(claims.get("scope")):
                errors.append("restore scope is missing")
        elif kind == CANDIDATE_KIND:
            if claims.get("validation_passed") is not True:
                errors.append("candidate validation did not pass")
            if claims.get("identity_verified_distinct") is not True:
                errors.append("candidate identity is not strongly distinct")
            if claims.get("member_of_pool") is not False:
                errors.append("candidate pool non-membership is not proven")
            if claims.get("contains_preserved_data") is not False:
                errors.append("candidate data disposition is not safe")
            capacity = claims.get("capacity_bytes")
            minimum = claims.get("minimum_capacity_bytes")
            if (
                not isinstance(capacity, int)
                or isinstance(capacity, bool)
                or not isinstance(minimum, int)
                or isinstance(minimum, bool)
                or capacity < minimum
            ):
                errors.append("candidate capacity is not proven sufficient")

        item = {
            "kind": kind,
            "statement_sha256": statement.get("statement_sha256"),
            "provider": _dict(_dict(statement.get("predicate")).get("provider")),
            "evidence_maturity": _dict(statement.get("predicate")).get(
                "evidence_maturity"
            ),
            "errors": list(dict.fromkeys(errors)),
        }
        (rejected if errors else accepted).append(item)

    accepted_kinds = [item["kind"] for item in accepted]
    contradictions = [
        f"multiple accepted {kind} attestations require explicit selection"
        for kind in KNOWN_KINDS
        if accepted_kinds.count(kind) > 1
    ]
    missing = [kind for kind in sorted(KNOWN_KINDS) if kind not in accepted_kinds]
    ready = not rejected and not contradictions and not missing
    modes = {
        item["provider"].get("mode")
        for item in accepted
        if item["provider"].get("mode")
    }
    maturity = "unverified"
    if accepted:
        maturity = (
            "deterministic_lab_fixture"
            if "deterministic_fixture" in modes
            else "passive_provider_evidence"
        )
    ledger = {
        "schema_version": 1,
        "incident_id": incident_id,
        "status": "EVIDENCE_READY" if ready else "HOLD",
        "accepted": accepted,
        "rejected": rejected,
        "missing_kinds": missing,
        "contradictions": contradictions,
        "evidence_maturity": maturity,
        "digest_authenticates_provider": False,
        "read_only": True,
        "control_authority": False,
    }
    ledger["ledger_sha256"] = _digest(ledger)
    return ledger


__all__ = [
    "BACKUP_KIND",
    "CANDIDATE_KIND",
    "collect_recovery_attestations",
    "issue_recovery_attestation",
    "reconcile_recovery_attestations",
    "validate_recovery_attestation",
]
