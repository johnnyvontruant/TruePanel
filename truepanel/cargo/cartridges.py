"""Read-only Loadmaster cartridge registry and Cargo Bay planning.

This module deliberately performs no mounts, copies, deletes, or unmounts.
It answers two questions for Cargo Bay:

* Which removable cartridge owns a canonical NAS media path?
* How much recent, not-yet-verified cargo is waiting for each cartridge?

Physical transfer authority belongs to the Loadmaster executor, not this
registry/planning layer.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOADMASTER_REGISTRY_SCHEMA_VERSION = 1
LOADMASTER_REGISTRY_KIND = "truepanel.loadmaster_cartridge_registry"


def _canonical_lexical(path: Path) -> Path:
    """Normalize dot components without resolving symlinks."""

    return Path(os.path.normpath(str(path)))


def _is_under(candidate: Path, prefix: Path) -> bool:
    try:
        candidate.relative_to(prefix)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class CartridgeDefinition:
    """One removable backup cartridge known to Loadmaster."""

    cartridge_id: str
    label: str
    uuid: str
    role: str
    source_prefix: Path
    usb_relative_path: Path
    device_serial: str | None = None
    allow_ingest: bool = True
    allow_backup: bool = True
    delete_policy: str = "never"

    def __post_init__(self) -> None:
        if not self.cartridge_id.strip():
            raise ValueError("cartridge id is required")
        if not self.label.strip():
            raise ValueError("cartridge label is required")
        if not self.uuid.strip():
            raise ValueError("cartridge uuid is required")
        if not self.role.strip():
            raise ValueError("cartridge role is required")
        if not self.source_prefix.is_absolute():
            raise ValueError("cartridge source_prefix must be absolute")
        if self.usb_relative_path.is_absolute():
            raise ValueError("cartridge usb_relative_path must be relative")

        normalized_usb = _canonical_lexical(self.usb_relative_path)
        if normalized_usb == Path(".") or ".." in normalized_usb.parts:
            raise ValueError("cartridge usb_relative_path is invalid")

        if self.delete_policy != "never":
            raise ValueError("Loadmaster delete_policy must be 'never'")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CartridgeDefinition":
        if not isinstance(payload, dict):
            raise ValueError("cartridge entry must be an object")

        source = str(payload.get("source_prefix") or "").strip()
        usb_path = str(payload.get("usb_relative_path") or "").strip()

        if not source:
            raise ValueError("cartridge source_prefix is required")
        if not usb_path:
            raise ValueError("cartridge usb_relative_path is required")

        return cls(
            cartridge_id=str(payload.get("id") or "").strip(),
            label=str(payload.get("label") or "").strip(),
            uuid=str(payload.get("uuid") or "").strip(),
            role=str(payload.get("role") or "").strip(),
            source_prefix=_canonical_lexical(Path(source)),
            usb_relative_path=_canonical_lexical(Path(usb_path)),
            device_serial=(
                str(
                    payload.get("device_serial")
                    or ""
                ).strip()
                or None
            ),
            allow_ingest=payload.get("allow_ingest") is not False,
            allow_backup=payload.get("allow_backup") is not False,
            delete_policy=str(payload.get("delete_policy") or "never").strip(),
        )

    def public_dict(self) -> dict[str, Any]:
        """Return non-sensitive cartridge identity for Mission Control."""

        return {
            "id": self.cartridge_id,
            "label": self.label,
            "role": self.role,
            "source_prefix": str(self.source_prefix),
            "usb_relative_path": str(self.usb_relative_path),
            "allow_ingest": self.allow_ingest,
            "allow_backup": self.allow_backup,
            "delete_policy": self.delete_policy,
        }


def load_cartridge_registry(path: Path) -> list[CartridgeDefinition]:
    """Load and validate a fail-closed cartridge registry."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError("missing Loadmaster cartridge registry") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            f"invalid Loadmaster cartridge registry: {error}"
        ) from error

    if not isinstance(payload, dict):
        raise ValueError("Loadmaster cartridge registry must be an object")

    if payload.get("schema_version") != LOADMASTER_REGISTRY_SCHEMA_VERSION:
        raise ValueError("unsupported Loadmaster cartridge registry schema")

    if payload.get("kind") != LOADMASTER_REGISTRY_KIND:
        raise ValueError("Loadmaster cartridge registry kind is invalid")

    entries = payload.get("cartridges")
    if not isinstance(entries, list):
        raise ValueError("Loadmaster cartridges must be a list")

    cartridges = [CartridgeDefinition.from_dict(item) for item in entries]

    ids: set[str] = set()
    uuids: set[str] = set()
    labels: set[str] = set()

    for cartridge in cartridges:
        if cartridge.cartridge_id in ids:
            raise ValueError(
                f"duplicate Loadmaster cartridge id: {cartridge.cartridge_id}"
            )
        ids.add(cartridge.cartridge_id)

        uuid_key = cartridge.uuid.casefold()
        if uuid_key in uuids:
            raise ValueError(
                f"duplicate Loadmaster cartridge uuid: {cartridge.uuid}"
            )
        uuids.add(uuid_key)

        label_key = cartridge.label.casefold()
        if label_key in labels:
            raise ValueError(
                f"duplicate Loadmaster cartridge label: {cartridge.label}"
            )
        labels.add(label_key)

    return cartridges


def assign_cartridge(
    media_path: Path | str,
    cartridges: list[CartridgeDefinition],
) -> CartridgeDefinition | None:
    """Return the most-specific cartridge owning ``media_path``."""

    path = _canonical_lexical(Path(media_path))

    if not path.is_absolute():
        return None

    matches = [
        cartridge
        for cartridge in cartridges
        if _is_under(
            path,
            _canonical_lexical(cartridge.source_prefix),
        )
    ]

    if not matches:
        return None

    return max(
        matches,
        key=lambda item: len(item.source_prefix.parts),
    )


def _backup_state_by_path(
    backup: dict[str, Any] | None,
) -> dict[str, str]:
    result: dict[str, str] = {}

    if not isinstance(backup, dict):
        return result

    for item in backup.get("items") or []:
        if not isinstance(item, dict):
            continue

        path = str(item.get("current_path") or "").strip()
        state = str(item.get("state") or "UNKNOWN").strip().upper()

        if path.startswith("/"):
            result[str(_canonical_lexical(Path(path)))] = state

    return result


def summarize_cartridge_cargo(
    *,
    cargo_items: list[dict[str, Any]],
    backup: dict[str, Any] | None,
    cartridges: list[CartridgeDefinition],
) -> dict[str, Any]:
    """Build read-only per-cartridge pending Cargo Bay telemetry."""

    backup_states = _backup_state_by_path(backup)

    rows: dict[str, dict[str, Any]] = {
        cartridge.cartridge_id: {
            **cartridge.public_dict(),
            "pending_items": 0,
            "pending_bytes": 0,
            "verified_items": 0,
            "review_items": 0,
            "items": [],
        }
        for cartridge in cartridges
    }

    unmapped = []
    pending_total = 0
    pending_bytes = 0

    for item in cargo_items:
        if not isinstance(item, dict):
            continue

        path_text = str(item.get("current_path") or "").strip()

        if not path_text.startswith("/"):
            unmapped.append(
                {
                    "title": item.get("title"),
                    "current_path": path_text or None,
                    "reason": "INVALID_PATH",
                }
            )
            continue

        canonical = str(_canonical_lexical(Path(path_text)))
        cartridge = assign_cartridge(canonical, cartridges)

        if cartridge is None:
            unmapped.append(
                {
                    "title": item.get("title"),
                    "current_path": canonical,
                    "reason": "NO_CARTRIDGE",
                }
            )
            continue

        backup_state = backup_states.get(canonical, "AWAITING")
        size = item.get("size_bytes")
        try:
            size_bytes = max(0, int(size or 0))
        except (TypeError, ValueError):
            size_bytes = 0

        row = rows[cartridge.cartridge_id]

        public_item = {
            "title": item.get("title"),
            "detail": item.get("detail"),
            "source": item.get("source"),
            "current_path": canonical,
            "size_bytes": size_bytes,
            "backup_state": backup_state,
        }

        row["items"].append(public_item)

        if backup_state == "VERIFIED":
            row["verified_items"] += 1
            continue

        row["pending_items"] += 1
        row["pending_bytes"] += size_bytes
        pending_total += 1
        pending_bytes += size_bytes

        if backup_state in {"MISMATCH", "STALE", "INVALID"}:
            row["review_items"] += 1

    ordered = [
        rows[cartridge.cartridge_id]
        for cartridge in cartridges
    ]

    pending_cartridges = [
        row for row in ordered
        if row["pending_items"] > 0
    ]

    pending_cartridges.sort(
        key=lambda row: (
            -int(row["pending_items"]),
            -int(row["pending_bytes"]),
            str(row["label"]).casefold(),
        )
    )

    review_count = sum(
        int(row["review_items"])
        for row in ordered
    )

    if unmapped or review_count:
        state = "REVIEW"
    elif pending_total:
        state = "AWAITING"
    else:
        state = "CLEAR"

    next_cartridge = (
        {
            "id": pending_cartridges[0]["id"],
            "label": pending_cartridges[0]["label"],
            "pending_items": pending_cartridges[0]["pending_items"],
            "pending_bytes": pending_cartridges[0]["pending_bytes"],
        }
        if pending_cartridges
        else None
    )

    return {
        "enabled": True,
        "read_only": True,
        "state": state,
        "pending_items": pending_total,
        "pending_bytes": pending_bytes,
        "review_items": review_count,
        "unmapped_items": len(unmapped),
        "next_cartridge": next_cartridge,
        "cartridges": ordered,
        "unmapped": unmapped,
    }


def unavailable_loadmaster_summary(
    reason: str,
) -> dict[str, Any]:
    return {
        "enabled": True,
        "read_only": True,
        "state": "INVALID",
        "pending_items": 0,
        "pending_bytes": 0,
        "review_items": 0,
        "unmapped_items": 0,
        "next_cartridge": None,
        "cartridges": [],
        "unmapped": [],
        "invalid_reason": str(reason),
    }


def disabled_loadmaster_summary() -> dict[str, Any]:
    return {
        "enabled": False,
        "read_only": True,
        "state": "DISABLED",
        "pending_items": 0,
        "pending_bytes": 0,
        "review_items": 0,
        "unmapped_items": 0,
        "next_cartridge": None,
        "cartridges": [],
        "unmapped": [],
    }
