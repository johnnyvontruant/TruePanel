"""
Privacy-safe TruePanel compatibility support bundles.

Support bundles contain compatibility observations only. They deliberately
exclude hostnames, network addresses, hardware serial numbers, WWIDs, MAC
addresses, usernames, configuration secrets, and pool contents.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from truepanel import __version__

from .models import CompatibilityReport


SUPPORT_BUNDLE_SCHEMA_VERSION = 1

PRIVACY_CONTRACT = {
    "hostname": "excluded",
    "ip_addresses": "excluded",
    "serial_numbers": "excluded",
    "wwids": "excluded",
    "mac_addresses": "excluded",
    "usernames": "excluded",
    "configuration_secrets": "excluded",
    "pool_contents": "excluded",
}


def build_support_bundle(
    report: CompatibilityReport,
    *,
    generated_at: datetime | None = None,
) -> dict:
    """
    Build a deterministic privacy-safe compatibility support payload.
    """

    timestamp = generated_at or datetime.now(timezone.utc)

    return {
        "schema_version": SUPPORT_BUNDLE_SCHEMA_VERSION,
        "truepanel_version": __version__,
        "generated_at": timestamp.isoformat(),
        "privacy": dict(PRIVACY_CONTRACT),
        "compatibility": report.to_dict(),
    }


def default_support_path(
    *,
    generated_at: datetime | None = None,
) -> Path:
    timestamp = generated_at or datetime.now(timezone.utc)

    suffix = timestamp.strftime(
        "%Y%m%d-%H%M%S"
    )

    return Path(
        f"truepanel-support-{suffix}.json"
    )


def write_support_bundle(
    report: CompatibilityReport,
    *,
    output: str | Path | None = None,
    generated_at: datetime | None = None,
) -> Path:
    """
    Write a privacy-safe support bundle and return its final path.
    """

    timestamp = generated_at or datetime.now(timezone.utc)

    destination = (
        Path(output)
        if output is not None
        else default_support_path(
            generated_at=timestamp
        )
    )

    destination = destination.expanduser()

    if destination.parent != Path("."):
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    payload = build_support_bundle(
        report,
        generated_at=timestamp,
    )

    destination.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return destination


def support_bundle_contains_forbidden_keys(
    payload: dict,
) -> set[str]:
    """
    Defensive test/helper for fields that must never enter support bundles.
    """

    forbidden = {
        "hostname",
        "ip",
        "ip_address",
        "ip_addresses",
        "serial",
        "serial_number",
        "wwid",
        "wwn",
        "mac",
        "mac_address",
        "username",
        "password",
        "token",
        "secret",
    }

    found: set[str] = set()

    def walk(value) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = str(key).strip().lower()

                # The top-level privacy manifest intentionally names excluded
                # data classes. Those declarations are not leaked values.
                if value is not payload.get("privacy"):
                    if normalized in forbidden:
                        found.add(normalized)

                walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)

    return found


__all__ = [
    "PRIVACY_CONTRACT",
    "SUPPORT_BUNDLE_SCHEMA_VERSION",
    "build_support_bundle",
    "default_support_path",
    "support_bundle_contains_forbidden_keys",
    "write_support_bundle",
]
