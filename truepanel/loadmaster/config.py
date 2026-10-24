"""Loadmaster settings, read from the top-level ``loadmaster:`` section.

Example::

    loadmaster:
      enabled: true
      state_dir: /var/lib/truepanel/loadmaster
      drives:
        - name: Movies 1-D
          nas_path: /mnt/HDDs/Movies/Movies 1-D
        - name: TV A-M
          nas_path: /mnt/HDDs/Shows/TV A-M

A drive is recognised by its filesystem **label**, which must equal its
``name``. Its files live in a folder of the same name on the drive
(``usb_folder``; set it to ``""`` if they sit at the drive root).

Sonarr and Radarr connection details are shared with Cargo Bay
(``mission_control.cargo_bay.sonarr`` / ``radarr``) so they are configured once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from truepanel.cargo.resolver import ServarrConfig

from .link import COMMAND_SOCKET, STATUS_PATH

DEFAULT_STATE_DIR = Path("/var/lib/truepanel/loadmaster")
DEFAULT_MOUNT_ROOT = Path("/mnt/loadmaster")
REPLACED_FOLDER = ".loadmaster-replaced"


class LoadmasterConfigError(ValueError):
    """The loadmaster: configuration section is invalid."""


@dataclass(frozen=True)
class Drive:
    """One USB drive and the NAS folder it mirrors."""

    name: str
    nas_path: Path
    usb_folder: str

    @property
    def key(self) -> str:
        """Filesystem-safe identifier used for state files and mountpoints."""

        return "".join(ch.lower() if ch.isalnum() else "-" for ch in self.name).strip(
            "-"
        )

    @property
    def replaced_dir(self) -> Path:
        """Where NAS files Loadmaster would overwrite or retire are moved."""

        return self.nas_path / REPLACED_FOLDER

    def usb_root(self, mountpoint: Path) -> Path:
        return mountpoint / self.usb_folder if self.usb_folder else mountpoint

    def public(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "key": self.key,
            "nas_path": str(self.nas_path),
            "usb_folder": self.usb_folder,
        }


@dataclass(frozen=True)
class Settings:
    drives: tuple[Drive, ...]
    state_dir: Path = DEFAULT_STATE_DIR
    mount_root: Path = DEFAULT_MOUNT_ROOT
    remote_start: bool = False
    copy_button: bool = True
    verify: str = "sha256"
    ingest_owner: tuple[int, int] | None = None
    large_delete_files: int = 100
    dock_poll_seconds: float = 3.0
    servarr_poll_seconds: float = 300.0
    pending_scan_seconds: float = 600.0
    sonarr: ServarrConfig | None = None
    radarr: ServarrConfig | None = None
    status_path: Path = STATUS_PATH
    command_socket: Path = COMMAND_SOCKET
    extra: dict[str, Any] = field(default_factory=dict)

    def drive_named(self, name: str) -> Drive | None:
        wanted = name.strip().casefold()
        for drive in self.drives:
            if drive.name.casefold() == wanted:
                return drive
        return None

    def drive_for_path(self, path: Path) -> Drive | None:
        """The drive whose NAS folder contains ``path`` (folders never overlap)."""

        for drive in self.drives:
            if path == drive.nas_path or drive.nas_path in path.parents:
                return drive
        return None


def _abs_path(value: Any, field_name: str) -> Path:
    text = str(value or "").strip()
    if not text.startswith("/"):
        raise LoadmasterConfigError(f"loadmaster {field_name} must be absolute")
    return Path(text)


def _servarr(section: Any, name: str) -> ServarrConfig | None:
    if not isinstance(section, dict):
        return None
    url = str(section.get("url") or "").strip()
    config_path = str(section.get("config_path") or "").strip()
    host_prefix = str(section.get("host_prefix") or "").strip()
    if not (url and config_path and host_prefix):
        return None
    return ServarrConfig(
        name=name,
        base_url=url,
        config_path=Path(config_path),
        media_prefix=str(section.get("media_prefix") or "").strip(),
        host_prefix=Path(host_prefix),
    )


def _owner(value: Any) -> tuple[int, int] | None:
    text = str(value or "").strip()
    if not text:
        return None
    uid, _, gid = text.partition(":")
    try:
        return int(uid), int(gid or uid)
    except ValueError as error:
        raise LoadmasterConfigError(
            "loadmaster ingest_owner must be uid:gid"
        ) from error


def load_settings(config: dict[str, Any]) -> Settings | None:
    """Return settings when Loadmaster is enabled, else ``None``."""

    section = config.get("loadmaster")
    if not isinstance(section, dict) or section.get("enabled") is not True:
        return None

    raw_drives = section.get("drives")
    if not isinstance(raw_drives, list) or not raw_drives:
        raise LoadmasterConfigError("loadmaster drives must be a non-empty list")

    drives: list[Drive] = []
    for raw in raw_drives:
        if not isinstance(raw, dict):
            raise LoadmasterConfigError("each loadmaster drive must be a mapping")
        name = str(raw.get("name") or "").strip()
        if not name:
            raise LoadmasterConfigError("loadmaster drive name is required")
        folder = raw.get("usb_folder", name)
        folder = "" if folder is None else str(folder).strip().strip("/")
        if folder and any(part in {"", ".", ".."} for part in folder.split("/")):
            raise LoadmasterConfigError(f"loadmaster usb_folder is invalid: {folder}")
        drives.append(
            Drive(
                name=name,
                nas_path=_abs_path(raw.get("nas_path"), f"{name} nas_path"),
                usb_folder=str(PurePosixPath(folder)) if folder else "",
            )
        )

    names = [drive.name.casefold() for drive in drives]
    if len(set(names)) != len(names):
        raise LoadmasterConfigError("loadmaster drive names must be unique")
    keys = [drive.key for drive in drives]
    if len(set(keys)) != len(keys) or "" in keys:
        raise LoadmasterConfigError("loadmaster drive names must differ by letters")
    for drive in drives:
        for other in drives:
            if drive is not other and (
                drive.nas_path == other.nas_path
                or drive.nas_path in other.nas_path.parents
            ):
                raise LoadmasterConfigError(
                    f"loadmaster nas_path overlaps: {drive.name} / {other.name}"
                )

    verify = str(section.get("verify") or "sha256").strip()
    if verify not in {"sha256", "size"}:
        raise LoadmasterConfigError("loadmaster verify must be sha256 or size")

    cargo = (config.get("mission_control") or {}).get("cargo_bay") or {}

    return Settings(
        drives=tuple(drives),
        state_dir=_abs_path(section.get("state_dir") or DEFAULT_STATE_DIR, "state_dir"),
        mount_root=_abs_path(
            section.get("mount_root") or DEFAULT_MOUNT_ROOT, "mount_root"
        ),
        remote_start=section.get("remote_start", False) is True,
        copy_button=section.get("copy_button", True) is not False,
        verify=verify,
        ingest_owner=_owner(section.get("ingest_owner")),
        large_delete_files=max(1, int(section.get("large_delete_files") or 100)),
        dock_poll_seconds=float(section.get("dock_poll_seconds") or 3.0),
        servarr_poll_seconds=float(section.get("servarr_poll_seconds") or 300.0),
        pending_scan_seconds=float(section.get("pending_scan_seconds") or 600.0),
        sonarr=_servarr(cargo.get("sonarr"), "sonarr"),
        radarr=_servarr(cargo.get("radarr"), "radarr"),
    )


__all__ = [
    "Drive",
    "LoadmasterConfigError",
    "REPLACED_FOLDER",
    "Settings",
    "load_settings",
]
