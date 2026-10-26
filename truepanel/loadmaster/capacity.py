"""Drive health and "full in N weeks" forecasts.

At plug-in Loadmaster reads the drive's size and free space and, through
``smartctl -j``, its SMART health: pass/fail, temperature, power-on hours and
SSD wear. USB bridges often need ``-d sat``, so that is tried too; a drive
that cannot report SMART is simply ``unavailable``.

The drive mirrors its NAS folder, so the NAS folder's growth is the drive's
growth. The service already scans every NAS folder every few minutes; once a
day per drive it logs the folder's size, and a straight-line fit over the
last 60 days, against the drive's capacity, gives the forecast.

Everything is kept in ``state_dir/capacity.jsonl``:
``{"kind": "nas", "drive", "time", "nas_bytes"}`` and
``{"kind": "drive", "drive", "time", "capacity_bytes", "free_bytes", "smart"}``.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

DAY = 86400.0
WINDOW_DAYS = 60
MIN_SPAN_DAYS = 3
FULL_AT = 0.98  # exFAT and the copy need a little headroom
LOG_NAME = "capacity.jsonl"
MAX_LINES = 20000

Runner = Callable[[Sequence[str]], str]


# ------------------------------------------------------------------ SMART


def _run(argv: Sequence[str]) -> str:
    done = subprocess.run(
        list(argv), capture_output=True, text=True, timeout=60, check=False
    )
    return done.stdout


def parse_smart(payload: dict[str, Any]) -> dict[str, Any] | None:
    """The fields that matter from ``smartctl -j``, or None if it saw nothing."""

    status = payload.get("smart_status") or {}
    if "passed" not in status:
        return None
    health: dict[str, Any] = {
        "status": "PASSED" if status["passed"] else "FAILED",
        "model": payload.get("model_name") or "",
        "temperature_c": (payload.get("temperature") or {}).get("current"),
        "power_on_hours": (payload.get("power_on_time") or {}).get("hours"),
        "percent_used": None,
    }
    nvme = payload.get("nvme_smart_health_information_log") or {}
    if isinstance(nvme.get("percentage_used"), int):
        health["percent_used"] = nvme["percentage_used"]
    else:
        # ATA SSDs: the normalised value of a wear attribute counts down from 100.
        for attribute in (payload.get("ata_smart_attributes") or {}).get("table", []):
            if attribute.get("id") in (202, 233, 231, 177, 173) and isinstance(
                attribute.get("value"), int
            ):
                health["percent_used"] = max(0, min(100, 100 - attribute["value"]))
                break
    return health


def read_smart(disk: str, runner: Runner = _run) -> dict[str, Any]:
    for extra in ((), ("-d", "sat")):
        try:
            output = runner(["smartctl", "-j", "-i", "-H", "-A", *extra, disk])
            health = parse_smart(json.loads(output or "{}"))
        except (OSError, ValueError, subprocess.SubprocessError):
            health = None
        if health is not None:
            return health
    return {"status": "unavailable"}


def disk_of(partition: str, runner: Runner = _run) -> str:
    """/dev/sda2 -> /dev/sda (SMART is read from the whole disk)."""

    try:
        parent = runner(["lsblk", "-no", "PKNAME", partition]).strip().splitlines()
    except (OSError, subprocess.SubprocessError):
        parent = []
    return f"/dev/{parent[0].strip()}" if parent and parent[0].strip() else partition


def space(mount: Path) -> tuple[int, int]:
    """(capacity, free) in bytes for the filesystem holding ``mount``."""

    stats = os.statvfs(mount)
    return stats.f_blocks * stats.f_frsize, stats.f_bavail * stats.f_frsize


# --------------------------------------------------------------- the log


class CapacityLog:
    def __init__(
        self, state_dir: Path, *, clock: Callable[[], float] = time.time
    ) -> None:
        self.path = state_dir / LOG_NAME
        self.clock = clock
        self._lock = threading.Lock()

    def _read(self) -> list[dict[str, Any]]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        entries = []
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict):
                entries.append(entry)
        return entries

    def _append(self, entry: dict[str, Any]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            entries = self._read()
            if len(entries) >= MAX_LINES:  # keep it bounded: drop the oldest tenth
                keep = entries[MAX_LINES // 10 :]
                self.path.write_text(
                    "".join(json.dumps(e, sort_keys=True) + "\n" for e in keep),
                    encoding="utf-8",
                )
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")

    def record_nas(self, drive: str, nas_bytes: int) -> bool:
        """Log the NAS folder size, at most once a day per drive."""

        now = self.clock()
        last = max(
            (
                e["time"]
                for e in self._read()
                if e.get("kind") == "nas" and e.get("drive") == drive
            ),
            default=None,
        )
        if last is not None and now - last < DAY:
            return False
        self._append(
            {"kind": "nas", "drive": drive, "time": now, "nas_bytes": int(nas_bytes)}
        )
        return True

    def record_drive(
        self, drive: str, *, capacity_bytes: int, free_bytes: int, smart: dict[str, Any]
    ) -> None:
        self._append(
            {
                "kind": "drive",
                "drive": drive,
                "time": self.clock(),
                "capacity_bytes": int(capacity_bytes),
                "free_bytes": int(free_bytes),
                "smart": smart,
            }
        )

    def summary(self, drive: str) -> dict[str, Any]:
        """What Mission Control and selftest show for one drive."""

        entries = [e for e in self._read() if e.get("drive") == drive]
        checks = [e for e in entries if e.get("kind") == "drive"]
        samples = [
            (e["time"], e["nas_bytes"]) for e in entries if e.get("kind") == "nas"
        ]
        result: dict[str, Any] = {}
        if checks:
            last = checks[-1]
            result.update(
                capacity_bytes=last["capacity_bytes"],
                checked=last["time"],
                smart=last.get("smart") or {"status": "unavailable"},
            )
        if samples:
            result["nas_bytes"] = samples[-1][1]
        if checks and samples:
            result["used_fraction"] = samples[-1][1] / max(
                1, checks[-1]["capacity_bytes"]
            )
            result["full_in_days"] = forecast(
                samples, checks[-1]["capacity_bytes"], self.clock()
            )
        return result


def forecast(
    samples: list[tuple[float, int]], capacity: int, now: float
) -> float | None:
    """Days until the folder outgrows ``capacity``; None without enough history
    or when it is not growing."""

    recent = [(t, b) for t, b in samples if now - t <= WINDOW_DAYS * DAY]
    if len(recent) < 2 or (recent[-1][0] - recent[0][0]) < MIN_SPAN_DAYS * DAY:
        return None
    n = len(recent)
    mean_t = sum(t for t, _ in recent) / n
    mean_b = sum(b for _, b in recent) / n
    spread = sum((t - mean_t) ** 2 for t, _ in recent)
    slope = sum((t - mean_t) * (b - mean_b) for t, b in recent) / spread  # bytes/second
    if slope <= 0:
        return None
    room = capacity * FULL_AT - recent[-1][1]
    return max(0.0, room / slope / DAY)


__all__ = [
    "CapacityLog",
    "disk_of",
    "forecast",
    "parse_smart",
    "read_smart",
    "space",
]
