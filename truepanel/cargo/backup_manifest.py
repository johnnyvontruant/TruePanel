"""
Read-only validation for Cargo Bay backup evidence.

Cargo Bay never infers backup completion from filesystem layout,
Lifeline acknowledgement, or TruePanel upgrade receipts. Backup
state requires an explicit Cargo backup manifest.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CARGO_BACKUP_MANIFEST_SCHEMA_VERSION = 1
CARGO_BACKUP_MANIFEST_KIND = "truepanel.cargo_backup_manifest"


def load_backup_manifest(
    manifest_path: Path,
) -> dict[str, Any]:
    try:
        payload = json.loads(
            manifest_path.read_text(
                encoding="utf-8",
            )
        )
    except FileNotFoundError as error:
        raise ValueError(
            "missing Cargo backup manifest"
        ) from error
    except (
        OSError,
        json.JSONDecodeError,
    ) as error:
        raise ValueError(
            f"invalid Cargo backup manifest: {error}"
        ) from error

    if not isinstance(payload, dict):
        raise ValueError(
            "Cargo backup manifest must be an object"
        )

    return payload


def validate_backup_manifest(
    manifest_path: Path,
) -> dict[str, Any]:
    payload = load_backup_manifest(
        manifest_path
    )

    if (
        payload.get("schema_version")
        != CARGO_BACKUP_MANIFEST_SCHEMA_VERSION
    ):
        raise ValueError(
            "unsupported Cargo backup manifest schema"
        )

    if (
        payload.get("kind")
        != CARGO_BACKUP_MANIFEST_KIND
    ):
        raise ValueError(
            "Cargo backup manifest kind is invalid"
        )

    created_at = payload.get("created_at")
    if (
        not isinstance(created_at, str)
        or not created_at.strip()
    ):
        raise ValueError(
            "Cargo backup manifest created_at is invalid"
        )

    source = payload.get("source")
    if (
        not isinstance(source, str)
        or not source.strip()
    ):
        raise ValueError(
            "Cargo backup manifest source is invalid"
        )

    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError(
            "Cargo backup manifest items must be a list"
        )

    normalized_items = []

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(
                "Cargo backup manifest item "
                f"{index} must be an object"
            )

        path = item.get("path")
        if (
            not isinstance(path, str)
            or not path.startswith("/")
        ):
            raise ValueError(
                "Cargo backup manifest item "
                f"{index} path is invalid"
            )

        size_bytes = item.get("size_bytes")
        if (
            isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or size_bytes < 0
        ):
            raise ValueError(
                "Cargo backup manifest item "
                f"{index} size_bytes is invalid"
            )

        backed_up_at = item.get(
            "backed_up_at"
        )
        if (
            not isinstance(backed_up_at, str)
            or not backed_up_at.strip()
        ):
            raise ValueError(
                "Cargo backup manifest item "
                f"{index} backed_up_at is invalid"
            )

        normalized = {
            "path": path,
            "size_bytes": size_bytes,
            "backed_up_at": backed_up_at,
        }

        sha256 = item.get("sha256")
        if sha256 is not None:
            if (
                not isinstance(sha256, str)
                or len(sha256) != 64
                or any(
                    character not in "0123456789abcdefABCDEF"
                    for character in sha256
                )
            ):
                raise ValueError(
                    "Cargo backup manifest item "
                    f"{index} sha256 is invalid"
                )

            normalized["sha256"] = (
                sha256.lower()
            )

        normalized_items.append(
            normalized
        )

    return {
        "schema_version": (
            CARGO_BACKUP_MANIFEST_SCHEMA_VERSION
        ),
        "kind": CARGO_BACKUP_MANIFEST_KIND,
        "created_at": created_at,
        "source": source,
        "items": normalized_items,
    }
