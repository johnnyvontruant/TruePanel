"""Fail-closed validation envelope for AEGIS production evidence.

The envelope answers a deliberately narrow question: does the currently
running reliability code still match the artifacts and safety contracts that
were accepted?  It does not authenticate an operator, sign evidence, or grant
recovery authority.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from truepanel import __version__

ASSURANCE_SCHEMA_VERSION = 1
DEFAULT_ENVELOPE_PATH = Path(__file__).with_name("assurance_envelope.json")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _iso_timestamp(value: str) -> float:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("assurance timestamps must include a timezone")
    return parsed.astimezone(UTC).timestamp()


def _condition(
    condition_type: str,
    status: str,
    reason: str,
    message: str,
) -> dict[str, str]:
    if status not in {"True", "False", "Unknown"}:
        raise ValueError("assurance condition status is invalid")
    return {
        "type": condition_type,
        "status": status,
        "reason": reason,
        "message": message,
    }


def load_assurance_envelope(path: Path | None = None) -> dict[str, Any]:
    """Load and minimally validate the packaged acceptance envelope."""

    source = path or DEFAULT_ENVELOPE_PATH
    try:
        raw = source.read_text(encoding="utf-8")
        envelope = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("AEGIS assurance envelope is unavailable") from error
    if not isinstance(envelope, dict):
        raise ValueError("AEGIS assurance envelope must be an object")
    if envelope.get("schema_version") != ASSURANCE_SCHEMA_VERSION:
        raise ValueError("unsupported AEGIS assurance envelope schema")
    if not str(envelope.get("envelope_id") or "").strip():
        raise ValueError("AEGIS assurance envelope ID is missing")
    subjects = envelope.get("subjects")
    if not isinstance(subjects, list) or not subjects:
        raise ValueError("AEGIS assurance envelope subjects are missing")
    return envelope


def coverage_contract_sha256(matrix: Mapping[str, Any]) -> str:
    """Digest the complete recovery-coverage contract deterministically."""

    return _sha256_bytes(_canonical(dict(matrix)))


def _runtime_subject_conditions(
    envelope: Mapping[str, Any],
    *,
    package_root: Path,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    conditions: list[dict[str, str]] = []
    observations: list[dict[str, str]] = []
    for item in envelope.get("subjects", []):
        if not isinstance(item, Mapping):
            conditions.append(
                _condition(
                    "RuntimeSubjectIntegrity",
                    "False",
                    "MalformedSubject",
                    "An assurance subject is malformed.",
                )
            )
            continue
        name = str(item.get("name") or "").strip()
        expected = str(item.get("sha256") or "").strip().lower()
        relative = Path(name)
        if (
            not name
            or relative.is_absolute()
            or ".." in relative.parts
            or len(expected) != 64
        ):
            conditions.append(
                _condition(
                    "RuntimeSubjectIntegrity",
                    "False",
                    "InvalidSubjectDescriptor",
                    "An assurance subject descriptor is unsafe.",
                )
            )
            continue
        path = package_root / relative
        try:
            observed = _sha256_file(path)
        except OSError:
            observed = ""
        matches = observed == expected
        observations.append(
            {
                "name": name,
                "expected_sha256": expected,
                "observed_sha256": observed or "unavailable",
                "status": "MATCH" if matches else "DRIFT",
            }
        )
        conditions.append(
            _condition(
                "RuntimeSubjectIntegrity",
                "True" if matches else "False",
                "DigestMatched" if matches else "DigestDrift",
                f"{name} {'matches' if matches else 'does not match'} the accepted digest.",
            )
        )
    return conditions, observations


def evaluate_airworthiness(
    *,
    payload: Mapping[str, Any],
    coverage_matrix: Mapping[str, Any],
    correlation_policy: Mapping[str, Any],
    now: float | None = None,
    envelope: Mapping[str, Any] | None = None,
    package_root: Path | None = None,
) -> dict[str, Any]:
    """Compare live contracts with a versioned, expiring acceptance envelope.

    Missing platform-version evidence is REVIEW rather than PASS.  Any known
    mismatch, expired envelope, incomplete recovery coverage, or subject
    digest drift is HOLD.  Raw alerts and recovery guidance remain visible in
    every state.
    """

    try:
        accepted = dict(
            load_assurance_envelope() if envelope is None else envelope
        )
        issued_at = _iso_timestamp(str(accepted["issued_at"]))
        expires_at = _iso_timestamp(str(accepted["expires_at"]))
    except (KeyError, TypeError, ValueError):
        return {
            "schema_version": ASSURANCE_SCHEMA_VERSION,
            "status": "HOLD",
            "reason": "EnvelopeUnavailable",
            "message": "The AEGIS acceptance envelope could not be validated.",
            "conditions": [],
            "subjects": [],
            "raw_alerts_retained": True,
            "recovery_guidance_visible": True,
            "production_mutation": False,
            "control_authority": False,
        }

    checked_at = _timestamp(now)
    if checked_at is None:
        checked_at = datetime.now(tz=UTC).timestamp()
    conditions: list[dict[str, str]] = []

    clock_sane = checked_at >= issued_at
    conditions.append(
        _condition(
            "ClockSane",
            "True" if clock_sane else "False",
            "ClockAccepted" if clock_sane else "ClockPredatesEnvelope",
            "Runtime clock does not predate the acceptance envelope."
            if clock_sane
            else "Runtime clock predates the accepted evidence.",
        )
    )
    fresh = issued_at <= checked_at < expires_at
    conditions.append(
        _condition(
            "EnvelopeFresh",
            "True" if fresh else "False",
            "InsideValidityWindow" if fresh else "EnvelopeExpired",
            "Acceptance evidence is inside its review window."
            if fresh
            else "Acceptance evidence requires a new review.",
        )
    )

    expected_version = str(accepted.get("truepanel_version") or "")
    version_matches = __version__ == expected_version
    conditions.append(
        _condition(
            "TruePanelVersionMatches",
            "True" if version_matches else "False",
            "VersionMatched" if version_matches else "VersionDrift",
            f"Running TruePanel {__version__}; accepted {expected_version or 'unknown'}.",
        )
    )

    expected_policy = str(accepted.get("correlation_policy_id") or "")
    observed_policy = str(correlation_policy.get("policy_id") or "")
    policy_matches = bool(expected_policy) and observed_policy == expected_policy
    conditions.append(
        _condition(
            "CorrelationPolicyMatches",
            "True" if policy_matches else "False",
            "PolicyMatched" if policy_matches else "PolicyDrift",
            f"Observed policy {observed_policy or 'unknown'}; accepted {expected_policy or 'unknown'}.",
        )
    )

    coverage_digest = coverage_contract_sha256(coverage_matrix)
    expected_coverage = str(accepted.get("coverage_sha256") or "")
    coverage_complete = (
        int(coverage_matrix.get("gaps", -1)) == 0
        and int(coverage_matrix.get("trusted", -1))
        == int(coverage_matrix.get("total", -2))
        and coverage_digest == expected_coverage
    )
    conditions.append(
        _condition(
            "RecoveryCoverageMatches",
            "True" if coverage_complete else "False",
            "CoverageMatched" if coverage_complete else "CoverageDrift",
            "Recovery coverage is complete and matches the accepted contract."
            if coverage_complete
            else "Recovery coverage is incomplete or differs from the accepted contract.",
        )
    )

    subject_conditions, subjects = _runtime_subject_conditions(
        accepted,
        package_root=package_root or Path(__file__).resolve().parents[1],
    )
    conditions.extend(subject_conditions)

    platform = payload.get("system")
    platform = platform if isinstance(platform, Mapping) else {}
    observed_platform = str(platform.get("truenas_version") or "").strip()
    expected_platform = str(accepted.get("platform_version") or "").strip()
    if not observed_platform:
        platform_status = "Unknown"
        platform_reason = "PlatformVersionUnobserved"
        platform_message = (
            f"Accepted platform is TrueNAS SCALE {expected_platform}; "
            "this snapshot does not expose a version fact."
        )
    else:
        matches = observed_platform == expected_platform
        platform_status = "True" if matches else "False"
        platform_reason = "PlatformMatched" if matches else "PlatformDrift"
        platform_message = (
            f"Observed TrueNAS {observed_platform}; accepted {expected_platform}."
        )
    conditions.append(
        _condition(
            "PlatformVersionMatches",
            platform_status,
            platform_reason,
            platform_message,
        )
    )

    false_conditions = [item for item in conditions if item["status"] == "False"]
    unknown_conditions = [item for item in conditions if item["status"] == "Unknown"]
    if false_conditions:
        status = "HOLD"
        reason = false_conditions[0]["reason"]
        message = (
            "Accepted AEGIS evidence has drifted or expired; revalidation is required."
        )
    elif unknown_conditions:
        status = "REVIEW"
        reason = unknown_conditions[0]["reason"]
        message = (
            "Code evidence matches, but a required live platform fact is unavailable."
        )
    else:
        status = "CURRENT"
        reason = "InsideValidatedEnvelope"
        message = "Observed contracts match the current acceptance envelope."

    return {
        "schema_version": ASSURANCE_SCHEMA_VERSION,
        "envelope_id": accepted.get("envelope_id"),
        "status": status,
        "reason": reason,
        "message": message,
        "issued_at": accepted.get("issued_at"),
        "expires_at": accepted.get("expires_at"),
        "checked_at": datetime.fromtimestamp(checked_at, tz=UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "platform_scope": f"TrueNAS SCALE {expected_platform}",
        "conditions": conditions,
        "subjects": subjects,
        "evidence_subjects": list(accepted.get("evidence_subjects", [])),
        "raw_alerts_retained": True,
        "recovery_guidance_visible": True,
        "production_mutation": False,
        "control_authority": False,
        "provenance": {
            "adapted_semantics": [
                "Kubernetes status conditions",
                "TUF expiration and subject hashes",
                "in-toto subject digests",
            ],
            "external_code_incorporated": False,
        },
    }


def validate_repository_evidence(
    root: Path,
    *,
    envelope: Mapping[str, Any] | None = None,
) -> tuple[str, ...]:
    """CI contract for evidence subjects kept outside the installed package."""

    accepted = dict(
        load_assurance_envelope() if envelope is None else envelope
    )
    errors: list[str] = []
    for item in accepted.get("evidence_subjects", []):
        if not isinstance(item, Mapping):
            errors.append("malformed evidence subject")
            continue
        name = str(item.get("name") or "")
        expected = str(item.get("sha256") or "").lower()
        path = Path(name)
        if not name or path.is_absolute() or ".." in path.parts or len(expected) != 64:
            errors.append(f"unsafe evidence subject: {name or '<missing>'}")
            continue
        try:
            observed = _sha256_file(root / path)
        except OSError:
            errors.append(f"missing evidence subject: {name}")
            continue
        if observed != expected:
            errors.append(f"evidence digest drift: {name}")
    return tuple(errors)


__all__ = [
    "ASSURANCE_SCHEMA_VERSION",
    "DEFAULT_ENVELOPE_PATH",
    "coverage_contract_sha256",
    "evaluate_airworthiness",
    "load_assurance_envelope",
    "validate_repository_evidence",
]
