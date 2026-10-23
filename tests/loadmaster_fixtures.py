"""Shared on-disk fixtures for Loadmaster pipeline tests."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from truepanel.cargo.backlog import empty_backlog
from truepanel.cargo.cartridges import CartridgeDefinition
from truepanel.cargo.loadmaster import FileFingerprint, scan_tree

MTIME = 1_700_000_000_000_000_000


@dataclass
class Bay:
    root: Path
    nas_root: Path
    usb_mount: Path
    usb_root: Path
    cartridge: CartridgeDefinition

    def write(
        self, base: Path, relative: str, data: bytes, mtime_ns: int = MTIME
    ) -> Path:
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        os.utime(path, ns=(mtime_ns, mtime_ns))
        return path

    def nas(self, relative: str, data: bytes, mtime_ns: int = MTIME) -> Path:
        return self.write(self.nas_root, relative, data, mtime_ns)

    def usb(self, relative: str, data: bytes, mtime_ns: int = MTIME) -> Path:
        return self.write(self.usb_root, relative, data, mtime_ns)

    def baseline(self) -> dict[str, FileFingerprint]:
        """Commission now: NAS inventory is the zero-delta baseline."""

        return scan_tree(self.nas_root)

    def backlog(self, *relatives: str) -> dict:
        payload = empty_backlog(observe_after=datetime(2026, 1, 1, tzinfo=UTC))
        stamp = "2026-10-01T00:00:00+00:00"
        for relative in relatives:
            path = self.nas_root / relative
            payload["items"].append(
                {
                    "title": relative,
                    "detail": None,
                    "source": "radarr",
                    "current_path": str(path),
                    "size_bytes": path.stat().st_size,
                    "source_imported_at": None,
                    "first_seen_at": stamp,
                    "last_seen_at": stamp,
                    "required_after": stamp,
                }
            )
        return payload


def make_bay(tmp_path: Path, **overrides) -> Bay:
    nas_root = tmp_path / "nas" / "Movies E-I"
    usb_mount = tmp_path / "usb"
    usb_root = usb_mount / "Movies E-I"
    nas_root.mkdir(parents=True)
    usb_root.mkdir(parents=True)
    payload = {
        "cartridge_id": "movies-e-i",
        "label": "Movies E-I",
        "uuid": "6989-100A",
        "role": "movies",
        "source_prefix": nas_root,
        "usb_relative_path": Path("Movies E-I"),
    }
    payload.update(overrides)
    return Bay(
        root=tmp_path,
        nas_root=nas_root,
        usb_mount=usb_mount,
        usb_root=usb_root,
        cartridge=CartridgeDefinition(**payload),
    )
