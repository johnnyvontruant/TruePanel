"""State-only Loadmaster commissioning helpers.

Commissioning can capture a NAS-side inventory only when an operator has
already proven that the corresponding USB cartridge is zero-delta using the
same size/mtime semantics. The snapshot becomes the conflict-detection
baseline for later Loadmaster plans.

No removable media is mounted or modified here.
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

from .cartridges import load_cartridge_registry
from .loadmaster import inventory_payload, scan_tree

ZERO_DELTA_CONFIRMATION = "CONFIRM_ZERO_DELTA_BASELINE"


class LoadmasterCommissionError(RuntimeError):
    """Fail-closed commissioning error."""


def _write_json_atomic(
    path: Path,
    payload: dict[str, Any],
) -> None:
    if not path.is_absolute():
        raise LoadmasterCommissionError(
            "commissioning output path must be absolute"
        )

    parent = path.parent

    if not parent.exists():
        raise LoadmasterCommissionError(
            f"commissioning output parent does not exist: {parent}"
        )

    if not parent.is_dir():
        raise LoadmasterCommissionError(
            f"commissioning output parent is not a directory: {parent}"
        )

    serialized = (
        json.dumps(
            payload,
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
        raise LoadmasterCommissionError(
            f"commissioning state write failed: {error}"
        ) from error

    finally:
        if (
            temporary is not None
            and temporary.exists()
        ):
            with suppress(OSError):
                temporary.unlink()


def capture_zero_delta_baselines(
    *,
    registry_path: Path,
    inventory_dir: Path,
    confirmation: str,
    captured_at: datetime | None = None,
) -> dict[str, Any]:
    """Capture NAS metadata as the proven zero-delta cartridge baseline."""

    if confirmation != ZERO_DELTA_CONFIRMATION:
        raise LoadmasterCommissionError(
            "zero-delta confirmation phrase is required"
        )

    if not inventory_dir.is_absolute():
        raise LoadmasterCommissionError(
            "inventory directory must be absolute"
        )

    if not inventory_dir.exists():
        raise LoadmasterCommissionError(
            f"inventory directory does not exist: {inventory_dir}"
        )

    if not inventory_dir.is_dir():
        raise LoadmasterCommissionError(
            f"inventory path is not a directory: {inventory_dir}"
        )

    cartridges = load_cartridge_registry(
        registry_path
    )

    if not cartridges:
        raise LoadmasterCommissionError(
            "cartridge registry is empty"
        )

    now = captured_at or datetime.now(UTC)

    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    timestamp = now.astimezone(
        UTC
    ).isoformat()

    reports = []

    for cartridge in cartridges:
        files = scan_tree(
            cartridge.source_prefix
        )

        payload = inventory_payload(
            cartridge=cartridge,
            files=files,
            captured_at=timestamp,
        )

        output = (
            inventory_dir
            / f"{cartridge.cartridge_id}.json"
        )

        if output.exists():
            raise LoadmasterCommissionError(
                "refusing to overwrite existing "
                f"inventory: {output}"
            )

        _write_json_atomic(
            output,
            payload,
        )

        reports.append(
            {
                "cartridge_id": (
                    cartridge.cartridge_id
                ),
                "label": cartridge.label,
                "source_prefix": str(
                    cartridge.source_prefix
                ),
                "inventory_path": str(
                    output
                ),
                "files": len(files),
                "bytes": sum(
                    item.size_bytes
                    for item in files.values()
                ),
            }
        )

    return {
        "state": "BASELINE_CAPTURED",
        "captured_at": timestamp,
        "confirmation": (
            ZERO_DELTA_CONFIRMATION
        ),
        "cartridges": reports,
    }


def run(
    argv: list[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Capture state-only Loadmaster zero-delta "
            "commissioning inventories."
        )
    )
    parser.add_argument(
        "--registry",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--inventory-dir",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--confirm",
        required=True,
    )

    args = parser.parse_args(argv)

    try:
        report = capture_zero_delta_baselines(
            registry_path=args.registry,
            inventory_dir=args.inventory_dir,
            confirmation=args.confirm,
        )
    except (
        ValueError,
        LoadmasterCommissionError,
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
