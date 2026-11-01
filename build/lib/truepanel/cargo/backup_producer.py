"""
Independent Cargo Bay backup evidence producer.

This module does not perform backups.

It observes a completed backup destination and emits explicit,
read-only evidence for Cargo Bay. Its only filesystem mutation is
an atomic replacement of the requested manifest output file.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import tempfile
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .backup_manifest import (
    CARGO_BACKUP_MANIFEST_KIND,
    CARGO_BACKUP_MANIFEST_SCHEMA_VERSION,
)


class BackupProducerError(RuntimeError):
    """Fail-closed producer error."""


@dataclass(frozen=True)
class BackupMapping:
    """Map one BattleStation media prefix to one backup prefix."""

    source_prefix: Path
    backup_prefix: Path

    def __post_init__(self) -> None:
        if not self.source_prefix.is_absolute():
            raise ValueError(
                "source prefix must be absolute"
            )

        if not self.backup_prefix.is_absolute():
            raise ValueError(
                "backup prefix must be absolute"
            )


def _canonical_lexical(path: Path) -> Path:
    """
    Normalize dot components without resolving symlinks.

    We deliberately avoid Path.resolve() because the producer must
    not silently follow an attacker-controlled or unexpected link.
    """

    return Path(
        os.path.normpath(
            str(path)
        )
    )


def _is_under(
    candidate: Path,
    prefix: Path,
) -> bool:
    try:
        candidate.relative_to(prefix)
    except ValueError:
        return False

    return True


def map_backup_path(
    source_path: Path,
    mappings: list[BackupMapping],
) -> Path | None:
    source = _canonical_lexical(
        source_path
    )

    matches: list[
        tuple[int, BackupMapping]
    ] = []

    for mapping in mappings:
        prefix = _canonical_lexical(
            mapping.source_prefix
        )

        if _is_under(source, prefix):
            matches.append(
                (
                    len(prefix.parts),
                    mapping,
                )
            )

    if not matches:
        return None

    _, selected = max(
        matches,
        key=lambda item: item[0],
    )

    source_prefix = _canonical_lexical(
        selected.source_prefix
    )
    backup_prefix = _canonical_lexical(
        selected.backup_prefix
    )

    relative = source.relative_to(
        source_prefix
    )

    destination = _canonical_lexical(
        backup_prefix / relative
    )

    if not _is_under(
        destination,
        backup_prefix,
    ):
        raise BackupProducerError(
            "mapped backup path escaped backup root"
        )

    return destination


def _cargo_items(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    cargo = payload.get("cargo_bay")

    if isinstance(cargo, dict):
        payload = cargo

    groups = payload.get("groups")

    if not isinstance(groups, dict):
        raise BackupProducerError(
            "Cargo payload groups are unavailable"
        )

    result = []

    for name in ("tv", "movies"):
        items = groups.get(name)

        if items is None:
            continue

        if not isinstance(items, list):
            raise BackupProducerError(
                f"Cargo group {name} is invalid"
            )

        for item in items:
            if not isinstance(item, dict):
                raise BackupProducerError(
                    f"Cargo group {name} "
                    "contains an invalid item"
                )

            result.append(item)

    return result


def _inspect_backup_file(
    path: Path,
) -> os.stat_result | None:
    """
    Inspect one backup destination without following a final symlink.
    """

    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise BackupProducerError(
            f"backup destination unreadable: {path}: {error}"
        ) from error

    if stat.S_ISLNK(info.st_mode):
        raise BackupProducerError(
            f"backup destination is a symlink: {path}"
        )

    if not stat.S_ISREG(info.st_mode):
        raise BackupProducerError(
            f"backup destination is not a regular file: {path}"
        )

    return info


def build_backup_manifest(
    *,
    cargo_payload: dict[str, Any],
    mappings: list[BackupMapping],
    observed_at: datetime | None = None,
    source_label: str = "truepanel-cargo-backup-producer",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Observe current backup copies and return manifest plus report.

    Missing copies are intentionally omitted from manifest evidence.
    Cargo Bay will therefore classify them as AWAITING.

    Existing copies with a different size are included using the
    observed backup size. Cargo Bay will classify those as MISMATCH.
    """

    if not mappings:
        raise BackupProducerError(
            "at least one backup mapping is required"
        )

    if observed_at is None:
        observed_at = datetime.now(UTC)

    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(
            tzinfo=UTC
        )

    observed_at = observed_at.astimezone(
        UTC
    )

    timestamp = observed_at.isoformat()

    manifest_items = []
    report_items = []

    for cargo_item in _cargo_items(
        cargo_payload
    ):
        current_path_text = str(
            cargo_item.get("current_path")
            or ""
        ).strip()

        if not current_path_text:
            raise BackupProducerError(
                "Cargo item has no current_path"
            )

        source_path = Path(
            current_path_text
        )

        if not source_path.is_absolute():
            raise BackupProducerError(
                f"Cargo path is not absolute: {source_path}"
            )

        expected_size = cargo_item.get(
            "size_bytes"
        )

        if (
            isinstance(expected_size, bool)
            or not isinstance(
                expected_size,
                int,
            )
            or expected_size < 0
        ):
            raise BackupProducerError(
                f"Cargo item size is invalid: {source_path}"
            )

        backup_path = map_backup_path(
            source_path,
            mappings,
        )

        if backup_path is None:
            report_items.append(
                {
                    "source_path": str(
                        source_path
                    ),
                    "backup_path": None,
                    "state": "UNMAPPED",
                    "expected_size": expected_size,
                    "observed_size": None,
                }
            )
            continue

        info = _inspect_backup_file(
            backup_path
        )

        if info is None:
            report_items.append(
                {
                    "source_path": str(
                        source_path
                    ),
                    "backup_path": str(
                        backup_path
                    ),
                    "state": "MISSING",
                    "expected_size": expected_size,
                    "observed_size": None,
                }
            )
            continue

        observed_size = int(
            info.st_size
        )

        state = (
            "VERIFIED"
            if observed_size
            == expected_size
            else "MISMATCH"
        )

        manifest_items.append(
            {
                "path": str(source_path),
                "size_bytes": observed_size,
                "backed_up_at": timestamp,
            }
        )

        report_items.append(
            {
                "source_path": str(
                    source_path
                ),
                "backup_path": str(
                    backup_path
                ),
                "state": state,
                "expected_size": expected_size,
                "observed_size": observed_size,
            }
        )

    manifest = {
        "schema_version": (
            CARGO_BACKUP_MANIFEST_SCHEMA_VERSION
        ),
        "kind": CARGO_BACKUP_MANIFEST_KIND,
        "created_at": timestamp,
        "source": source_label,
        "items": manifest_items,
    }

    counts = {
        "VERIFIED": 0,
        "MISMATCH": 0,
        "MISSING": 0,
        "UNMAPPED": 0,
    }

    for item in report_items:
        state = item["state"]

        if state in counts:
            counts[state] += 1

    report = {
        "observed_at": timestamp,
        "source": source_label,
        "total": len(report_items),
        "evidence_items": len(
            manifest_items
        ),
        "verified": counts["VERIFIED"],
        "mismatch": counts["MISMATCH"],
        "missing": counts["MISSING"],
        "unmapped": counts["UNMAPPED"],
        "items": report_items,
    }

    return manifest, report


def write_manifest_atomic(
    path: Path,
    manifest: dict[str, Any],
) -> None:
    """
    Atomically replace one manifest.

    No backup/media files are modified.
    """

    if not path.is_absolute():
        raise BackupProducerError(
            "manifest output path must be absolute"
        )

    parent = path.parent

    if not parent.exists():
        raise BackupProducerError(
            f"manifest parent does not exist: {parent}"
        )

    if not parent.is_dir():
        raise BackupProducerError(
            f"manifest parent is not a directory: {parent}"
        )

    serialized = (
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    temporary: Path | None = None

    try:
        descriptor, temporary_name = (
            tempfile.mkstemp(
                prefix=f".{path.name}.",
                suffix=".tmp",
                dir=parent,
                text=True,
            )
        )

        temporary = Path(
            temporary_name
        )

        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write(
                serialized
            )
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
        raise BackupProducerError(
            f"manifest write failed: {error}"
        ) from error

    finally:
        if (
            temporary is not None
            and temporary.exists()
        ):
            with suppress(OSError):
                temporary.unlink()


def parse_mapping(
    value: str,
) -> BackupMapping:
    source, separator, backup = (
        value.partition("=")
    )

    if not separator:
        raise argparse.ArgumentTypeError(
            "mapping must be SOURCE=BACKUP"
        )

    source_path = Path(
        source.strip()
    )
    backup_path = Path(
        backup.strip()
    )

    try:
        return BackupMapping(
            source_prefix=source_path,
            backup_prefix=backup_path,
        )
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            str(error)
        ) from error


def load_cargo_json(
    path: Path,
) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as error:
        raise BackupProducerError(
            f"unable to load Cargo JSON: {error}"
        ) from error

    if not isinstance(payload, dict):
        raise BackupProducerError(
            "Cargo JSON must be an object"
        )

    return payload


def run(
    argv: list[str] | None = None,
    *,
    clock: Callable[[], datetime]
    | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Observe independent backup copies "
            "and emit Cargo Bay evidence."
        )
    )

    parser.add_argument(
        "--cargo-json",
        required=True,
        type=Path,
        help=(
            "Saved Mission Control status JSON "
            "or Cargo Bay payload"
        ),
    )

    parser.add_argument(
        "--map",
        dest="mappings",
        action="append",
        required=True,
        type=parse_mapping,
        help=(
            "Path mapping SOURCE_PREFIX=BACKUP_PREFIX; "
            "repeat as needed"
        ),
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help=(
            "Absolute output manifest path"
        ),
    )

    parser.add_argument(
        "--source-label",
        default=(
            "truepanel-cargo-backup-producer"
        ),
    )

    parser.add_argument(
        "--report",
        type=Path,
        help=(
            "Optional JSON observation report"
        ),
    )

    args = parser.parse_args(
        argv
    )

    payload = load_cargo_json(
        args.cargo_json
    )

    now = (
        clock()
        if clock is not None
        else datetime.now(UTC)
    )

    manifest, report = (
        build_backup_manifest(
            cargo_payload=payload,
            mappings=args.mappings,
            observed_at=now,
            source_label=args.source_label,
        )
    )

    write_manifest_atomic(
        args.output,
        manifest,
    )

    if args.report is not None:
        write_manifest_atomic(
            args.report,
            report,
        )

    print(
        "Cargo backup evidence written"
    )
    print(
        f"  total:     {report['total']}"
    )
    print(
        f"  verified:  {report['verified']}"
    )
    print(
        f"  mismatch:  {report['mismatch']}"
    )
    print(
        f"  missing:   {report['missing']}"
    )
    print(
        f"  unmapped:  {report['unmapped']}"
    )
    print(
        f"  evidence:  {report['evidence_items']}"
    )
    print(
        f"  manifest:  {args.output}"
    )

    return 0


def main() -> None:
    try:
        raise SystemExit(
            run()
        )
    except BackupProducerError as error:
        raise SystemExit(
            f"HOLD: {error}"
        ) from error


if __name__ == "__main__":
    main()
