"""16x2 front-panel pages for Loadmaster.

While a drive needs attention the LCD shows these pages instead of its normal
rotation. SELECT (down) steps through them, ENTER (up) ejects a drive that is
not copying, and the Copy button starts a READY sync. Pure functions of the
published status, so they are easy to test and identical in the virtual LCD.
"""

from __future__ import annotations

import textwrap
from typing import Any

from truepanel.display.widgets import progress_bar

WIDTH = 16
CLEAR_SHOWN_SECONDS = 60.0
TAKEOVER = frozenset(
    {
        "CHECKING",
        "READY",
        "CONFIRM",
        "HOLD",
        "NEW_DRIVE",
        "COPYING",
        "DONE",
        "PARTIAL",
        "FAILED",
        "STOPPED",
        "EJECTED",
    }
)
EJECT_ON_ENTER = frozenset({"READY", "CONFIRM", "CLEAR", "HOLD", "NEW_DRIVE"})
HINT = ["ENTER = Eject", "SELECT = Next"]


def size(value: Any) -> str:
    """Compact size: 950M, 12.4G, 2.1T."""

    number = float(value or 0)
    for unit, scale in (("T", 1e12), ("G", 1e9), ("M", 1e6), ("K", 1e3)):
        if number >= scale:
            n = number / scale
            return f"{n:.1f}{unit}" if n < 100 else f"{n:.0f}{unit}"
    return f"{int(number)}B"


def _fit(text: Any) -> str:
    return str(text or "")[:WIDTH]


def _title(status: dict[str, Any], word: str = "") -> str:
    name = str((status.get("drive") or {}).get("name") or "Loadmaster").upper()
    if not word:
        return _fit(name)
    return f"{name[: WIDTH - len(word) - 1]} {word}"


def _wrap(text: str) -> list[list[str]]:
    lines = textwrap.wrap(text or "", WIDTH)[:4] or ["See TruePanel"]
    if len(lines) % 2:
        lines.append("")
    return [lines[i : i + 2] for i in range(0, len(lines), 2)]


def _counts(summary: dict[str, Any]) -> list[str]:
    return [
        _fit(
            f"To USB {summary.get('to_usb_files', 0):>3} {size(summary.get('to_usb_bytes')):>5}"
        ),
        _fit(
            f"To NAS {summary.get('to_nas_files', 0):>3} {size(summary.get('to_nas_bytes')):>5}"
        ),
    ]


def takeover(status: dict[str, Any] | None, now: float) -> bool:
    if not status or not status.get("available"):
        return False
    state = status.get("state")
    if state == "CLEAR":
        return now - float(status.get("state_since") or 0) < CLEAR_SHOWN_SECONDS
    return state in TAKEOVER


def enter_ejects(status: dict[str, Any] | None) -> bool:
    return bool(
        status
        and status.get("available")
        and status.get("drive")
        and status.get("state") in EJECT_ON_ENTER
    )


def pages(status: dict[str, Any] | None) -> list[list[str]]:
    if not status or not status.get("available"):
        return []
    state = status.get("state")
    summary = (status.get("plan") or {}).get("summary") or {}
    removals = int(summary.get("delete_usb_files") or 0) + int(
        summary.get("retire_nas_files") or 0
    )

    if state == "CHECKING":
        return [[_title(status), "Checking..."]]
    if state == "READY":
        result = [[_title(status, "READY"), "Press COPY"], _counts(summary)]
        if removals:
            result.append([_fit(f"Remove {removals} old"), "files on USB"])
        return result + [HINT]
    if state == "CONFIRM":
        return [
            [_title(status), "Press COPY" if status.get("armed") else "Confirm in TP"],
            [_fit(f"Removes {removals}"), "old files"],
            _counts(summary),
            HINT,
        ]
    if state == "CLEAR":
        return [[_title(status), "Up to date"], HINT]
    if state == "COPYING":
        p = status.get("progress") or {}
        total, done = int(p.get("total_bytes") or 0), int(p.get("done_bytes") or 0)
        pct = int(done * 100 / total) if total else 0
        files = int(p.get("total_files") or 0)
        index = min(files, int(p.get("done_files") or 0) + 1)
        current = str(p.get("current") or "").rsplit("/", 1)[-1]
        return [
            [_fit(f"{_title(status)[:11]} {pct:>3}%"), progress_bar(pct)],
            [_fit(f"File {index}/{files}"), _fit(f"{size(done)}/{size(total)}")],
            [_fit(current or "Copying"), "Do not unplug"],
        ]
    if state == "DONE":
        run = (status.get("last_run") or {}).get("summary") or {}
        moved = int(run.get("to_usb_files") or 0) + int(run.get("to_nas_files") or 0)
        return [
            [_title(status, "DONE"), "Safe to remove"],
            [_fit(f"Copied {moved} files"), size(run.get("copied_bytes"))],
        ]
    if state in {"PARTIAL", "FAILED", "STOPPED"}:
        safe = "Safe to remove" if status.get("safe_to_remove") else "Do not unplug"
        return [[_title(status, state), safe], *_wrap(status.get("message") or "")]
    if state == "HOLD":
        return [
            [_title(status, "HOLD"), "Needs attention"],
            *_wrap(status.get("message") or ""),
            HINT,
        ]
    if state == "NEW_DRIVE":
        return [[_title(status), "Unknown drive"], ["Adopt it in", "TruePanel"], HINT]
    if state == "EJECTED":
        return [[_title(status), "Safe to remove"]]
    return []


def idle_page(status: dict[str, Any] | None) -> list[str]:
    """One page for the normal rotation: which drive to plug in next."""

    if not status or not status.get("available"):
        return ["Loadmaster", "Offline"]
    for drive in status.get("drives") or []:
        if drive.get("pending_files"):
            return [
                _fit(f"Next: {drive['name']}"),
                _fit(
                    f"{drive['pending_files']} new {size(drive.get('pending_bytes'))}"
                ),
            ]
    return ["Loadmaster", "All drives synced"]


__all__ = ["enter_ejects", "idle_page", "pages", "size", "takeover"]
