"""Sanitized, digest-bound witness for the running TrueNAS release."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Any

PLATFORM_WITNESS_SCHEMA = "truepanel.platform-witness/v1"
PLATFORM_VERSION_METHOD = "system.version"
_VERSION = re.compile(
    r"^(?:TrueNAS-(?:SCALE-)?)?"
    r"(?P<version>[0-9]{2}\.[0-9]{1,2}(?:\.[0-9]+)?"
    r"(?:-[A-Za-z0-9][A-Za-z0-9.-]*)?)$"
)
_ALLOWED_FIELDS = frozenset(
    {
        "schema",
        "method",
        "status",
        "reason",
        "truenas_version",
        "source",
        "age_seconds",
        "observed_at",
        "read_only",
        "sensitive_fields_retained",
        "runtime_writes",
        "production_mutation",
        "control_authority",
        "evidence_sha256",
    }
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(dict(value))).hexdigest()


def normalize_truenas_version(value: Any) -> str | None:
    """Return the release component from the documented scalar response."""

    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        return None
    if value != value.strip() or any(ord(character) < 32 for character in value):
        return None
    matched = _VERSION.fullmatch(value)
    return matched.group("version") if matched else None


def _finite_age(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return round(number, 3)


def _finite_timestamp(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def issue_platform_witness(
    client: Any,
    *,
    clock: Callable[[], float] = time.time,
) -> dict[str, Any]:
    """Read only ``system.version`` and emit a privacy-minimal observation."""

    raw = client.call(PLATFORM_VERSION_METHOD)
    metrics = client.metrics()
    source = str(metrics.get("last_source") or "unavailable")
    age = _finite_age(metrics.get("last_age_seconds"))
    version = normalize_truenas_version(raw)
    if raw is None:
        status = "REVIEW"
        reason = "PlatformVersionUnavailable"
    elif version is None:
        status = "HOLD"
        reason = "PlatformVersionMalformed"
    elif source == "stale_cache":
        status = "REVIEW"
        reason = "PlatformVersionStale"
    elif source not in {"live_read", "cache"}:
        status = "HOLD"
        reason = "PlatformSourceUntrusted"
    else:
        status = "VERIFIED"
        reason = "PlatformVersionWitnessed"

    observed_at = _finite_timestamp(clock())
    if observed_at is None:
        status = "HOLD"
        reason = "PlatformClockInvalid"

    witness = {
        "schema": PLATFORM_WITNESS_SCHEMA,
        "method": PLATFORM_VERSION_METHOD,
        "status": status,
        "reason": reason,
        "truenas_version": version,
        "source": source,
        "age_seconds": age,
        "observed_at": observed_at,
        "read_only": True,
        "sensitive_fields_retained": False,
        "runtime_writes": 0,
        "production_mutation": False,
        "control_authority": False,
    }
    witness["evidence_sha256"] = _digest(witness)
    return witness


def validate_platform_witness(value: Any) -> tuple[str, ...]:
    """Validate shape, safety invariants, normalized version, and digest."""

    if not isinstance(value, Mapping):
        return ("platform witness is missing",)
    witness = dict(value)
    errors: list[str] = []
    unknown = sorted(set(witness) - _ALLOWED_FIELDS)
    if unknown:
        errors.append("platform witness contains unapproved fields")
    if witness.get("schema") != PLATFORM_WITNESS_SCHEMA:
        errors.append("platform witness schema is invalid")
    if witness.get("method") != PLATFORM_VERSION_METHOD:
        errors.append("platform witness method is not allowlisted")
    if witness.get("status") not in {"VERIFIED", "REVIEW", "HOLD"}:
        errors.append("platform witness status is invalid")
    version = witness.get("truenas_version")
    if version is not None and normalize_truenas_version(version) != version:
        errors.append("platform witness version is not normalized")
    if witness.get("source") not in {
        "live_read",
        "cache",
        "stale_cache",
        "unavailable",
    }:
        errors.append("platform witness source is invalid")
    if _finite_age(witness.get("age_seconds")) != witness.get("age_seconds"):
        errors.append("platform witness age is invalid")
    if _finite_timestamp(witness.get("observed_at")) is None:
        errors.append("platform witness timestamp is invalid")
    if witness.get("read_only") is not True:
        errors.append("platform witness is not read-only")
    if witness.get("sensitive_fields_retained") is not False:
        errors.append("platform witness retained sensitive fields")
    if witness.get("runtime_writes") != 0:
        errors.append("platform witness reports runtime writes")
    if witness.get("production_mutation") is not False:
        errors.append("platform witness reports production mutation")
    if witness.get("control_authority") is not False:
        errors.append("platform witness reports control authority")
    if witness.get("status") == "VERIFIED" and (
        not version
        or witness.get("source") not in {"live_read", "cache"}
        or _finite_age(witness.get("age_seconds")) is None
    ):
        errors.append("verified platform witness lacks fresh version evidence")
    supplied = witness.pop("evidence_sha256", None)
    try:
        expected = _digest(witness)
    except (TypeError, ValueError):
        expected = ""
    if not isinstance(supplied, str) or supplied != expected:
        errors.append("platform witness digest is invalid")
    return tuple(errors)


def bind_platform_witness(
    payload: Mapping[str, Any],
    witness: Mapping[str, Any],
) -> dict[str, Any]:
    """Attach evidence and expose the version only after full validation."""

    result = deepcopy(dict(payload))
    system = result.get("system")
    system = deepcopy(system) if isinstance(system, dict) else {}
    original_errors = validate_platform_witness(witness)
    preserved = {
        field: deepcopy(witness[field])
        for field in sorted(_ALLOWED_FIELDS)
        if field in witness
    }
    if original_errors:
        preserved["status"] = "HOLD"
        preserved["reason"] = "PlatformWitnessInvalid"
        preserved.pop("evidence_sha256", None)
        preserved["evidence_sha256"] = _digest(preserved)
    system["platform_witness"] = preserved
    if not original_errors and preserved.get("status") == "VERIFIED":
        system["truenas_version"] = preserved.get("truenas_version")
    else:
        system.pop("truenas_version", None)
    result["system"] = system
    return result


__all__ = [
    "PLATFORM_VERSION_METHOD",
    "PLATFORM_WITNESS_SCHEMA",
    "bind_platform_witness",
    "issue_platform_witness",
    "normalize_truenas_version",
    "validate_platform_witness",
]
