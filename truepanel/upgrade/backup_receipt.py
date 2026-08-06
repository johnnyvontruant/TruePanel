"""
Self-describing metadata for retained TruePanel backups.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKUP_PREFIX = ".truepanel-backup-"
BACKUP_RECEIPT_NAME = (
    "truepanel-backup-receipt.json"
)
BACKUP_RECEIPT_SCHEMA_VERSION = 1

BACKUP_KINDS = {
    "promotion",
    "rollback_safety",
}


def utc_timestamp() -> str:
    return datetime.now(
        UTC
    ).isoformat()


def write_backup_receipt(
    *,
    backup_root: Path,
    deploy_root: Path,
    source_root: Path,
    kind: str,
) -> Path:
    backup_root = backup_root.resolve()
    deploy_root = deploy_root.resolve()
    source_root = source_root.resolve()

    if kind not in BACKUP_KINDS:
        raise ValueError(
            f"Unsupported backup kind: {kind}"
        )

    if not backup_root.is_dir():
        raise ValueError(
            f"Backup does not exist: "
            f"{backup_root}"
        )

    if (
        backup_root.parent
        != deploy_root.parent
    ):
        raise ValueError(
            "Backup must be a sibling of "
            "the deployment"
        )

    if not backup_root.name.startswith(
        BACKUP_PREFIX
    ):
        raise ValueError(
            "Backup name is unsafe"
        )

    payload = {
        "schema_version": (
            BACKUP_RECEIPT_SCHEMA_VERSION
        ),
        "kind": kind,
        "state": "retained",
        "created_at": utc_timestamp(),
        "backup_root": str(
            backup_root
        ),
        "deploy_root": str(
            deploy_root
        ),
        "source_root": str(
            source_root
        ),
    }

    receipt_path = (
        backup_root
        / BACKUP_RECEIPT_NAME
    )

    receipt_path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return receipt_path


def load_backup_receipt(
    backup_root: Path,
) -> dict[str, Any]:
    receipt_path = (
        backup_root
        / BACKUP_RECEIPT_NAME
    )

    try:
        payload = json.loads(
            receipt_path.read_text(
                encoding="utf-8"
            )
        )
    except FileNotFoundError as error:
        raise ValueError(
            "missing backup receipt"
        ) from error
    except (
        OSError,
        json.JSONDecodeError,
    ) as error:
        raise ValueError(
            f"invalid backup receipt: {error}"
        ) from error

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            "backup receipt must be an object"
        )

    return payload


def validate_backup_receipt(
    *,
    backup_root: Path,
    deploy_root: Path,
) -> dict[str, Any]:
    backup_root = backup_root.resolve()
    deploy_root = deploy_root.resolve()

    payload = load_backup_receipt(
        backup_root
    )

    if payload.get(
        "schema_version"
    ) != BACKUP_RECEIPT_SCHEMA_VERSION:
        raise ValueError(
            "unsupported backup receipt schema"
        )

    if payload.get(
        "state"
    ) != "retained":
        raise ValueError(
            "backup receipt is not retained"
        )

    if payload.get(
        "kind"
    ) not in BACKUP_KINDS:
        raise ValueError(
            "backup receipt kind is invalid"
        )

    receipt_backup = Path(
        str(
            payload.get(
                "backup_root",
                "",
            )
        )
    ).resolve()

    receipt_deploy = Path(
        str(
            payload.get(
                "deploy_root",
                "",
            )
        )
    ).resolve()

    if receipt_backup != backup_root:
        raise ValueError(
            "backup receipt path does not match"
        )

    if receipt_deploy != deploy_root:
        raise ValueError(
            "backup receipt deployment "
            "does not match"
        )

    if (
        backup_root.parent
        != deploy_root.parent
    ):
        raise ValueError(
            "backup is outside deployment parent"
        )

    if not backup_root.name.startswith(
        BACKUP_PREFIX
    ):
        raise ValueError(
            "backup name is unsafe"
        )

    return payload
