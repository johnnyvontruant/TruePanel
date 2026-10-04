"""State-only Loadmaster durable backlog observer.

The observer samples Cargo Bay's Servarr resolver and persists only backlog
state. It never mounts removable media and never copies, deletes, or unmounts
media. This lets physical Loadmaster authority remain disabled while newly
imported or replaced cargo is durably queued for later cartridge handling.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from truepanel.config.loader import load_config

from .backup_manifest import validate_backup_manifest
from .backlog import (
    LoadmasterBacklogError,
    load_backlog,
    reconcile_backlog,
    write_backlog_atomic,
)
from .cartridges import (
    CartridgeDefinition,
    assign_cartridge,
    load_cartridge_registry,
)
from .provider import CachedCargoProvider, provider_from_config


class LoadmasterObserverError(RuntimeError):
    """Fail-closed backlog observer error."""


def _cargo_items(
    payload: dict[str, Any],
    cartridges: list[CartridgeDefinition],
) -> tuple[list[dict[str, Any]], int]:
    groups = payload.get("groups")

    if not isinstance(groups, dict):
        raise LoadmasterObserverError(
            "Cargo resolver groups are unavailable"
        )

    configured_roles = {
        cartridge.role.casefold()
        for cartridge in cartridges
    }
    source_roles = {
        "radarr": "movies",
        "sonarr": "tv",
    }

    result = []
    ignored_out_of_scope = 0

    for name in ("tv", "movies"):
        values = groups.get(name)

        if values is None:
            continue

        if not isinstance(values, list):
            raise LoadmasterObserverError(
                f"Cargo group {name} is invalid"
            )

        for item in values:
            if not isinstance(item, dict):
                raise LoadmasterObserverError(
                    f"Cargo group {name} contains an invalid item"
                )

            source = str(
                item.get("source") or ""
            ).strip().casefold()
            role = source_roles.get(source)

            if (
                role is not None
                and role not in configured_roles
            ):
                ignored_out_of_scope += 1
                continue

            current_path = str(
                item.get("current_path") or ""
            ).strip()
            cartridge = assign_cartridge(
                current_path,
                cartridges,
            )

            if cartridge is None:
                raise LoadmasterObserverError(
                    "in-scope cargo has no cartridge mapping: "
                    f"{current_path or '(missing path)'}"
                )

            result.append(item)

    return result, ignored_out_of_scope


def observe_once(
    provider: CachedCargoProvider,
    *,
    observed_at: datetime | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Observe current Servarr cargo and reconcile the durable backlog."""

    backlog_path = provider.loadmaster_backlog_path
    registry_path = provider.cartridge_registry_path

    if backlog_path is None:
        raise LoadmasterObserverError(
            "Loadmaster backlog_path is not configured"
        )

    if registry_path is None:
        raise LoadmasterObserverError(
            "Loadmaster cartridge_registry_path is not configured"
        )

    try:
        previous = load_backlog(
            backlog_path
        )
    except LoadmasterBacklogError as error:
        raise LoadmasterObserverError(
            str(error)
        ) from error

    manifest = None
    manifest_path = provider.backup_manifest_path

    if manifest_path is not None:
        try:
            manifest = validate_backup_manifest(
                manifest_path
            )
        except ValueError as error:
            raise LoadmasterObserverError(
                str(error)
            ) from error

    try:
        cartridges = load_cartridge_registry(
            registry_path
        )
    except ValueError as error:
        raise LoadmasterObserverError(
            str(error)
        ) from error

    payload = provider.resolver.snapshot()

    if not isinstance(payload, dict):
        raise LoadmasterObserverError(
            "Cargo resolver returned a non-dict payload"
        )

    cargo_items, ignored_out_of_scope = (
        _cargo_items(
            payload,
            cartridges,
        )
    )

    backlog, report = reconcile_backlog(
        previous=previous,
        cargo_items=cargo_items,
        manifest=manifest,
        observed_at=observed_at,
    )

    if not dry_run:
        write_backlog_atomic(
            backlog_path,
            backlog,
        )

    result = dict(report)
    result["ignored_out_of_scope"] = (
        ignored_out_of_scope
    )
    result["dry_run"] = bool(dry_run)
    result["backlog_path"] = str(
        backlog_path
    )
    result["wrote_backlog"] = not dry_run

    return result


def run(
    argv: list[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Observe Cargo Bay and durably queue post-baseline "
            "Loadmaster backup work without actuating USB media."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("truepanel.yaml"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Reconcile and report without writing backlog state.",
    )

    args = parser.parse_args(argv)

    try:
        config = load_config(
            args.config
        )
        provider = provider_from_config(
            config
        )

        if provider is None:
            raise LoadmasterObserverError(
                "Cargo Bay configuration is unavailable"
            )

        report = observe_once(
            provider,
            dry_run=args.dry_run,
        )

    except (
        OSError,
        ValueError,
        LoadmasterObserverError,
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
