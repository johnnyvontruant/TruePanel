"""Durable pending-cargo ledger for Loadmaster.

The ledger exists so removable cartridges can stay offline longer than Cargo
Bay's bounded Servarr history window without pending backup work disappearing.

This module never mounts, copies, deletes, or unmounts media. Its only mutation
is an atomic replacement of the configured Loadmaster state file.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .backup_manifest import validate_backup_manifest

LOADMASTER_BACKLOG_SCHEMA_VERSION = 1
LOADMASTER_BACKLOG_KIND = "truepanel.loadmaster_backlog"


class LoadmasterBacklogError(RuntimeError):
    """Fail-closed durable-backlog error."""


def _canonical(path: Any) -> str:
    text = str(path or "").strip()

    if not text.startswith("/"):
        raise LoadmasterBacklogError(
            "Loadmaster backlog path must be absolute"
        )

    return str(Path(os.path.normpath(text)))


def _utc(value: datetime | None = None) -> datetime:
    value = value or datetime.now(UTC)

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat()


def _parse_iso(value: Any, *, field: str) -> datetime:
    text = str(value or "").strip()

    if not text:
        raise LoadmasterBacklogError(
            f"Loadmaster backlog {field} is invalid"
        )

    try:
        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise LoadmasterBacklogError(
            f"Loadmaster backlog {field} is invalid"
        ) from error

    return _utc(parsed)


def _imported_at(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, bool):
        raise LoadmasterBacklogError(
            "Loadmaster backlog imported_at is invalid"
        )

    try:
        timestamp = float(value)
    except (TypeError, ValueError) as error:
        raise LoadmasterBacklogError(
            "Loadmaster backlog imported_at is invalid"
        ) from error

    try:
        return datetime.fromtimestamp(
            timestamp,
            tz=UTC,
        )
    except (OverflowError, OSError, ValueError) as error:
        raise LoadmasterBacklogError(
            "Loadmaster backlog imported_at is invalid"
        ) from error


def _size(value: Any) -> int:
    if isinstance(value, bool):
        raise LoadmasterBacklogError(
            "Loadmaster backlog size_bytes is invalid"
        )

    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise LoadmasterBacklogError(
            "Loadmaster backlog size_bytes is invalid"
        ) from error

    if result < 0:
        raise LoadmasterBacklogError(
            "Loadmaster backlog size_bytes is invalid"
        )

    return result


def empty_backlog(
    *,
    updated_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": LOADMASTER_BACKLOG_SCHEMA_VERSION,
        "kind": LOADMASTER_BACKLOG_KIND,
        "updated_at": _iso(_utc(updated_at)),
        "items": [],
    }


def validate_backlog_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise LoadmasterBacklogError(
            "Loadmaster backlog must be an object"
        )

    if (
        payload.get("schema_version")
        != LOADMASTER_BACKLOG_SCHEMA_VERSION
    ):
        raise LoadmasterBacklogError(
            "unsupported Loadmaster backlog schema"
        )

    if payload.get("kind") != LOADMASTER_BACKLOG_KIND:
        raise LoadmasterBacklogError(
            "Loadmaster backlog kind is invalid"
        )

    updated_at = _iso(
        _parse_iso(
            payload.get("updated_at"),
            field="updated_at",
        )
    )

    items = payload.get("items")

    if not isinstance(items, list):
        raise LoadmasterBacklogError(
            "Loadmaster backlog items must be a list"
        )

    normalized = []
    seen: set[str] = set()

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise LoadmasterBacklogError(
                f"Loadmaster backlog item {index} must be an object"
            )

        path = _canonical(
            item.get("current_path")
        )

        if path in seen:
            raise LoadmasterBacklogError(
                f"duplicate Loadmaster backlog path: {path}"
            )

        seen.add(path)

        first_seen = _iso(
            _parse_iso(
                item.get("first_seen_at"),
                field="first_seen_at",
            )
        )
        last_seen = _iso(
            _parse_iso(
                item.get("last_seen_at"),
                field="last_seen_at",
            )
        )
        required_after = _iso(
            _parse_iso(
                item.get("required_after"),
                field="required_after",
            )
        )

        imported = item.get(
            "source_imported_at"
        )
        if imported is not None:
            _imported_at(imported)
            imported = float(imported)

        normalized.append(
            {
                "title": item.get("title"),
                "detail": item.get("detail"),
                "source": item.get("source"),
                "current_path": path,
                "size_bytes": _size(
                    item.get("size_bytes")
                ),
                "source_imported_at": imported,
                "first_seen_at": first_seen,
                "last_seen_at": last_seen,
                "required_after": required_after,
            }
        )

    return {
        "schema_version": LOADMASTER_BACKLOG_SCHEMA_VERSION,
        "kind": LOADMASTER_BACKLOG_KIND,
        "updated_at": updated_at,
        "items": normalized,
    }


def load_backlog(
    path: Path,
    *,
    missing_ok: bool = False,
) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8",
            )
        )
    except FileNotFoundError:
        if missing_ok:
            return empty_backlog()

        raise LoadmasterBacklogError(
            "missing Loadmaster backlog"
        )
    except (OSError, json.JSONDecodeError) as error:
        raise LoadmasterBacklogError(
            f"invalid Loadmaster backlog: {error}"
        ) from error

    return validate_backlog_payload(
        payload
    )


def _manifest_evidence(
    manifest: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}

    if not isinstance(manifest, dict):
        return evidence

    for item in manifest.get("items") or []:
        if not isinstance(item, dict):
            continue

        path = _canonical(
            item.get("path")
        )
        evidence[path] = item

    return evidence


def _upsert_item(
    *,
    recent: dict[str, Any],
    previous: dict[str, Any] | None,
    observed_at: datetime,
) -> dict[str, Any]:
    path = _canonical(
        recent.get("current_path")
    )
    size_bytes = _size(
        recent.get("size_bytes")
    )
    imported = _imported_at(
        recent.get("imported_at")
    )

    if previous is None:
        required = (
            imported
            if imported is not None
            else observed_at
        )
        first_seen = observed_at
    else:
        first_seen = _parse_iso(
            previous.get("first_seen_at"),
            field="first_seen_at",
        )
        required = _parse_iso(
            previous.get("required_after"),
            field="required_after",
        )

        previous_size = _size(
            previous.get("size_bytes")
        )
        previous_imported = _imported_at(
            previous.get(
                "source_imported_at"
            )
        )

        if size_bytes != previous_size:
            required = (
                imported
                if imported is not None
                else observed_at
            )
        elif (
            imported is not None
            and (
                previous_imported is None
                or imported > previous_imported
            )
        ):
            required = max(
                required,
                imported,
            )

    return {
        "title": recent.get("title"),
        "detail": recent.get("detail"),
        "source": recent.get("source"),
        "current_path": path,
        "size_bytes": size_bytes,
        "source_imported_at": (
            float(
                recent.get("imported_at")
            )
            if imported is not None
            else (
                previous.get(
                    "source_imported_at"
                )
                if previous
                else None
            )
        ),
        "first_seen_at": _iso(first_seen),
        "last_seen_at": _iso(observed_at),
        "required_after": _iso(required),
    }


def reconcile_backlog(
    *,
    previous: dict[str, Any] | None,
    cargo_items: list[dict[str, Any]],
    manifest: dict[str, Any] | None,
    observed_at: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Merge recent cargo and clear only explicitly verified backup evidence."""

    now = _utc(observed_at)

    if previous is None:
        current = empty_backlog(
            updated_at=now
        )
    else:
        current = validate_backlog_payload(
            previous
        )

    by_path = {
        item["current_path"]: dict(item)
        for item in current["items"]
    }

    observed = 0

    for recent in cargo_items:
        if not isinstance(recent, dict):
            raise LoadmasterBacklogError(
                "Loadmaster cargo item must be an object"
            )

        path = _canonical(
            recent.get("current_path")
        )

        by_path[path] = _upsert_item(
            recent=recent,
            previous=by_path.get(path),
            observed_at=now,
        )
        observed += 1

    evidence = _manifest_evidence(
        manifest
    )

    kept = []
    report_items = []
    verified = 0
    mismatch = 0
    stale = 0
    awaiting = 0

    for path in sorted(by_path):
        item = by_path[path]
        proof = evidence.get(path)
        state = "AWAITING"

        if proof is None:
            awaiting += 1
        elif _size(
            proof.get("size_bytes")
        ) != item["size_bytes"]:
            state = "MISMATCH"
            mismatch += 1
        else:
            backed_up_at = _parse_iso(
                proof.get("backed_up_at"),
                field="backed_up_at",
            )
            required_after = _parse_iso(
                item.get("required_after"),
                field="required_after",
            )

            if backed_up_at < required_after:
                state = "STALE"
                stale += 1
            else:
                state = "VERIFIED"
                verified += 1

        report_items.append(
            {
                "current_path": path,
                "title": item.get("title"),
                "size_bytes": item["size_bytes"],
                "state": state,
            }
        )

        if state != "VERIFIED":
            kept.append(item)

    payload = {
        "schema_version": LOADMASTER_BACKLOG_SCHEMA_VERSION,
        "kind": LOADMASTER_BACKLOG_KIND,
        "updated_at": _iso(now),
        "items": kept,
    }

    report = {
        "observed_at": _iso(now),
        "observed_items": observed,
        "previous_items": len(
            current["items"]
        ),
        "pending_items": len(kept),
        "verified": verified,
        "awaiting": awaiting,
        "stale": stale,
        "mismatch": mismatch,
        "items": report_items,
    }

    return payload, report


def write_backlog_atomic(
    path: Path,
    payload: dict[str, Any],
) -> None:
    """Atomically replace the state ledger without touching media."""

    if not path.is_absolute():
        raise LoadmasterBacklogError(
            "Loadmaster backlog output path must be absolute"
        )

    validated = validate_backlog_payload(
        payload
    )

    parent = path.parent

    if not parent.exists():
        raise LoadmasterBacklogError(
            f"Loadmaster backlog parent does not exist: {parent}"
        )

    if not parent.is_dir():
        raise LoadmasterBacklogError(
            f"Loadmaster backlog parent is not a directory: {parent}"
        )

    serialized = (
        json.dumps(
            validated,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    temporary: Path | None = None

    try:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=parent,
            text=True,
        )
        temporary = Path(name)

        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(
                handle.fileno()
            )

        os.replace(
            temporary,
            path,
        )
        temporary = None

        try:
            directory_fd = os.open(
                parent,
                os.O_RDONLY,
            )
        except OSError:
            directory_fd = None

        if directory_fd is not None:
            try:
                os.fsync(
                    directory_fd
                )
            finally:
                os.close(
                    directory_fd
                )

    except OSError as error:
        raise LoadmasterBacklogError(
            f"Loadmaster backlog write failed: {error}"
        ) from error

    finally:
        if (
            temporary is not None
            and temporary.exists()
        ):
            with suppress(OSError):
                temporary.unlink()


def _cargo_items(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    cargo = payload.get("cargo_bay")

    if isinstance(cargo, dict):
        payload = cargo

    groups = payload.get("groups")

    if not isinstance(groups, dict):
        raise LoadmasterBacklogError(
            "Cargo payload groups are unavailable"
        )

    result = []

    for name in ("tv", "movies"):
        values = groups.get(name)

        if values is None:
            continue

        if not isinstance(values, list):
            raise LoadmasterBacklogError(
                f"Cargo group {name} is invalid"
            )

        for item in values:
            if not isinstance(item, dict):
                raise LoadmasterBacklogError(
                    f"Cargo group {name} contains an invalid item"
                )

            result.append(item)

    return result


def run(
    argv: list[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Persist recent Cargo Bay items in the "
            "Loadmaster durable backlog."
        )
    )
    parser.add_argument(
        "--cargo-json",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--backlog",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--backup-manifest",
        type=Path,
    )

    args = parser.parse_args(argv)

    try:
        cargo_payload = json.loads(
            args.cargo_json.read_text(
                encoding="utf-8",
            )
        )

        previous = load_backlog(
            args.backlog,
            missing_ok=True,
        )

        manifest = (
            validate_backup_manifest(
                args.backup_manifest
            )
            if args.backup_manifest
            else None
        )

        payload, report = reconcile_backlog(
            previous=previous,
            cargo_items=_cargo_items(
                cargo_payload
            ),
            manifest=manifest,
        )

        write_backlog_atomic(
            args.backlog,
            payload,
        )

    except (
        OSError,
        json.JSONDecodeError,
        ValueError,
        LoadmasterBacklogError,
    ) as error:
        parser.exit(
            30,
            f"HOLD: {error}\n",
        )

    print(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
