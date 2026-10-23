"""Durable Loadmaster state: per-drive sync records and the activity log.

Each drive has a record of every file as it was the last time NAS and USB were
known to match. That record is what lets Loadmaster tell "deleted on the NAS"
(mirror the deletion to USB) apart from "new on USB" (bring it to the NAS)
without any manual commissioning. It is written atomically and only ever
describes files that were verified present and identical on both sides, so a
stale record is safe: the next plan simply re-learns the truth.

The activity log is an append-only JSON-lines file of Sonarr/Radarr events and
Loadmaster runs; it is what TruePanel shows as "what came in and what moved".
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .scan import Fingerprint

RECORD_SCHEMA = 1
ACTIVITY_MAX_BYTES = 5 * 1024 * 1024


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"), default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, 0o644)
        os.replace(name, path)
    except BaseException:
        with suppress(OSError):
            os.unlink(name)
        raise


@dataclass
class DriveRecord:
    """What one drive held the last time it was verified in sync."""

    name: str
    uuid: str | None = None
    serial: str | None = None
    last_sync: float | None = None
    files: dict[str, Fingerprint] = field(default_factory=dict)

    @property
    def known(self) -> bool:
        """True once a sync has completed (deletions can be inferred)."""

        return self.last_sync is not None

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": RECORD_SCHEMA,
            "name": self.name,
            "uuid": self.uuid,
            "serial": self.serial,
            "last_sync": self.last_sync,
            "files": {path: fp.to_list() for path, fp in sorted(self.files.items())},
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> DriveRecord:
        if payload.get("schema") != RECORD_SCHEMA:
            raise ValueError("unsupported Loadmaster record schema")
        files = {
            str(path): Fingerprint.from_list(value)
            for path, value in (payload.get("files") or {}).items()
        }
        last_sync = payload.get("last_sync")
        return cls(
            name=str(payload.get("name") or ""),
            uuid=payload.get("uuid") or None,
            serial=payload.get("serial") or None,
            last_sync=float(last_sync) if last_sync is not None else None,
            files=files,
        )


class StateStore:
    def __init__(self, root: Path, *, clock=time.time) -> None:
        self.root = root
        self.clock = clock
        self._log_lock = threading.Lock()

    # ------------------------------------------------------------ records

    def record_path(self, key: str) -> Path:
        return self.root / "drives" / f"{key}.json"

    def load_record(self, key: str, name: str) -> DriveRecord:
        path = self.record_path(key)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return DriveRecord(name=name)
        # A corrupt record raises: guessing would risk wrong mirror deletions.
        return DriveRecord.from_json(payload)

    def save_record(self, key: str, record: DriveRecord) -> None:
        write_json_atomic(self.record_path(key), record.to_json())

    # ------------------------------------------------------------- cursors

    def load_cursor(self, name: str) -> Any:
        try:
            return json.loads((self.root / "cursors.json").read_text()).get(name)
        except (FileNotFoundError, ValueError, AttributeError):
            return None

    def save_cursor(self, name: str, value: Any) -> None:
        path = self.root / "cursors.json"
        try:
            cursors = json.loads(path.read_text())
            if not isinstance(cursors, dict):
                cursors = {}
        except (FileNotFoundError, ValueError):
            cursors = {}
        cursors[name] = value
        write_json_atomic(path, cursors)

    # ------------------------------------------------------------ activity

    @property
    def activity_path(self) -> Path:
        return self.root / "activity.jsonl"

    def log(self, kind: str, **fields: Any) -> dict[str, Any]:
        entry = {"time": self.clock(), "kind": kind, **fields}
        line = json.dumps(entry, separators=(",", ":"), default=str) + "\n"
        with self._log_lock:
            self.root.mkdir(parents=True, exist_ok=True)
            path = self.activity_path
            with suppress(FileNotFoundError):
                if path.stat().st_size > ACTIVITY_MAX_BYTES:
                    os.replace(path, path.with_suffix(".jsonl.1"))
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)
        return entry

    def recent_activity(self, limit: int = 50) -> list[dict[str, Any]]:
        lines: deque[str] = deque(maxlen=limit)
        with (
            suppress(FileNotFoundError),
            self.activity_path.open(encoding="utf-8") as fh,
        ):
            for line in fh:
                lines.append(line)
        result = []
        for line in reversed(lines):
            with suppress(ValueError):
                result.append(json.loads(line))
        return result


__all__ = ["DriveRecord", "StateStore", "write_json_atomic"]
