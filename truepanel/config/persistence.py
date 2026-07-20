"""Atomic configuration persistence for TruePanel."""

from __future__ import annotations

import copy
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from .policy import ConfigurationPolicyService, NightModePolicy


class ConfigurationPersistenceError(RuntimeError):
    """Raised when a validated configuration cannot be persisted safely."""


@dataclass(frozen=True)
class PersistenceResult:
    changed: bool
    persisted: bool
    dry_run: bool
    path: str
    backup_path: str | None
    changed_fields: tuple[str, ...]
    proposed: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "persisted": self.persisted,
            "dry_run": self.dry_run,
            "path": self.path,
            "backup_path": self.backup_path,
            "changed_fields": list(self.changed_fields),
            "proposed": copy.deepcopy(self.proposed),
        }


class ConfigurationPersistenceService:
    """Validate and atomically persist supported TruePanel configuration."""

    def __init__(
        self,
        config_path: str | os.PathLike[str],
        config: Mapping[str, Any] | None = None,
        clock=None,
    ):
        self.config_path = Path(config_path)
        self.config = copy.deepcopy(dict(config or {}))
        self.clock = clock or time.time
        self._lock = threading.Lock()

    def preview_night_mode(
        self,
        patch: Mapping[str, Any],
    ):
        return ConfigurationPolicyService(
            self.config
        ).preview_night_mode(patch)

    def save_night_mode(
        self,
        patch: Mapping[str, Any],
        *,
        dry_run: bool = False,
    ) -> PersistenceResult:
        with self._lock:
            preview = self.preview_night_mode(patch)

            proposed_config = copy.deepcopy(self.config)
            flightdeck = proposed_config.setdefault(
                "flightdeck",
                {},
            )
            flightdeck["night_mode"] = (
                preview.proposed.as_dict()
            )

            if dry_run or not preview.changed:
                return PersistenceResult(
                    changed=preview.changed,
                    persisted=False,
                    dry_run=bool(dry_run),
                    path=str(self.config_path),
                    backup_path=None,
                    changed_fields=preview.changed_fields,
                    proposed=proposed_config,
                )

            self._validate_destination()

            backup_path = self._create_backup()
            self._atomic_write(proposed_config)

            self.config = proposed_config

            return PersistenceResult(
                changed=True,
                persisted=True,
                dry_run=False,
                path=str(self.config_path),
                backup_path=(
                    str(backup_path)
                    if backup_path is not None
                    else None
                ),
                changed_fields=preview.changed_fields,
                proposed=copy.deepcopy(proposed_config),
            )

    def _validate_destination(self) -> None:
        parent = self.config_path.parent

        if not parent.exists():
            raise ConfigurationPersistenceError(
                f"Configuration directory does not exist: {parent}"
            )

        if not parent.is_dir():
            raise ConfigurationPersistenceError(
                f"Configuration parent is not a directory: {parent}"
            )

        if self.config_path.exists():
            if not self.config_path.is_file():
                raise ConfigurationPersistenceError(
                    f"Configuration path is not a regular file: {self.config_path}"
                )

            if not os.access(self.config_path, os.W_OK):
                raise ConfigurationPersistenceError(
                    f"Configuration file is not writable: {self.config_path}"
                )
        elif not os.access(parent, os.W_OK):
            raise ConfigurationPersistenceError(
                f"Configuration directory is not writable: {parent}"
            )

    def _create_backup(self) -> Path | None:
        if not self.config_path.exists():
            return None

        timestamp = time.strftime(
            "%Y%m%d-%H%M%S",
            time.localtime(self.clock()),
        )
        backup_path = self.config_path.with_name(
            f"{self.config_path.name}.backup-{timestamp}"
        )

        counter = 1
        while backup_path.exists():
            backup_path = self.config_path.with_name(
                f"{self.config_path.name}.backup-{timestamp}-{counter}"
            )
            counter += 1

        backup_path.write_bytes(
            self.config_path.read_bytes()
        )
        return backup_path

    def _atomic_write(
        self,
        payload: Mapping[str, Any],
    ) -> None:
        parent = self.config_path.parent
        descriptor = None
        temporary_path = None

        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{self.config_path.name}.",
                suffix=".tmp",
                dir=parent,
                text=True,
            )
            temporary_path = Path(temporary_name)

            with os.fdopen(
                descriptor,
                "w",
                encoding="utf-8",
            ) as handle:
                descriptor = None
                yaml.safe_dump(
                    dict(payload),
                    handle,
                    sort_keys=False,
                    default_flow_style=False,
                )
                handle.flush()
                os.fsync(handle.fileno())

            if self.config_path.exists():
                mode = self.config_path.stat().st_mode & 0o777
                os.chmod(temporary_path, mode)

            os.replace(
                temporary_path,
                self.config_path,
            )

            directory_fd = os.open(
                parent,
                os.O_DIRECTORY,
            )
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise ConfigurationPersistenceError(
                f"Could not persist configuration: {exc}"
            ) from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)

            if (
                temporary_path is not None
                and temporary_path.exists()
            ):
                temporary_path.unlink()
