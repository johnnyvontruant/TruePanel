"""16x2 LCD pages for Loadmaster.

When a cartridge needs attention the front LCD switches to these pages so an
operator standing at the NAS can finish the job there:

* SELECT steps through the pages for the current state.
* ENTER ejects (unmounts) a docked cartridge that is READY, CLEAR, or on HOLD.
* The physical Copy button starts a READY transfer.

Pages are pure functions of the published Loadmaster status so they can be
tested without hardware and rendered identically by the virtual LCD in
Mission Control.
"""

from __future__ import annotations

from typing import Any

from truepanel.display.widgets import progress_bar

LCD_WIDTH = 16
CLEAR_TAKEOVER_SECONDS = 60.0

ATTENTION_STATES = frozenset(
    {
        "READY",
        "EXECUTING",
        "HOLD",
        "COMPLETE",
        "PARTIAL",
        "FAILED",
        "CANCELLED",
        "EJECTED",
        "UNREGISTERED",
    }
)
EJECTABLE_STATES = frozenset({"READY", "CLEAR", "HOLD"})

REASON_SHORT = {
    "NOT_COMMISSIONED": "Not commissioned",
    "IDENTITY_UNVERIFIED": "ID not verified",
    "MULTIPLE_CARTRIDGES": "One at a time",
    "MOUNT_FAILED": "Mount failed",
    "PLAN_HOLD": "Conflicts found",
    "PLAN_FAILED": "Plan failed",
    "DOCK_UNAVAILABLE": "Dock error",
    "ARM_FAILED": "Arm failed",
    "EJECT_FAILED": "Eject failed",
    "CONTROLLER_ERROR": "Internal error",
}


def _fit(text: Any) -> str:
    return str(text if text is not None else "")[:LCD_WIDTH]


def format_bytes(value: Any) -> str:
    """Compact size for a 16-character line: 950M, 12.4G, 2.1T."""

    try:
        size = float(value or 0)
    except (TypeError, ValueError):
        size = 0.0
    for unit, scale in (("T", 1e12), ("G", 1e9), ("M", 1e6), ("K", 1e3)):
        if size >= scale:
            number = size / scale
            return f"{number:.1f}{unit}" if number < 100 else f"{number:.0f}{unit}"
    return f"{int(size)}B"


def _label(status: dict[str, Any]) -> str:
    cartridge = status.get("cartridge") or {}
    return str(cartridge.get("label") or "Loadmaster").upper()


def _head(status: dict[str, Any], word: str) -> str:
    label = _label(status)
    room = LCD_WIDTH - len(word) - 1
    return f"{label[:room]} {word}"


def _short_reason(reason: Any) -> str:
    text = str(reason or "")
    code = text.split(":", 1)[0].strip()
    return REASON_SHORT.get(code, text[:LCD_WIDTH] or "See TruePanel")


def _count_line(direction: str, files: int, size: Any) -> str:
    return _fit(f"{direction} {files:>3} {format_bytes(size):>5}")


def loadmaster_takeover(status: dict[str, Any] | None, now: float) -> bool:
    """Should the LCD show Loadmaster instead of the normal rotation?"""

    if not status or not status.get("available"):
        return False
    state = status.get("state")
    if state in ATTENTION_STATES:
        return True
    if state == "CLEAR":
        since = float(status.get("state_since") or 0)
        return now - since < CLEAR_TAKEOVER_SECONDS
    return False


def loadmaster_enter_action(status: dict[str, Any] | None) -> str | None:
    if not status or not status.get("available"):
        return None
    if status.get("state") in EJECTABLE_STATES and status.get("cartridge"):
        return "eject"
    return None


def loadmaster_pages(status: dict[str, Any] | None) -> list[list[str]]:
    """Return the LCD pages for the current Loadmaster state."""

    if not status or not status.get("available"):
        return []

    state = str(status.get("state") or "")
    plan = status.get("plan") or {}
    summary = plan.get("summary") or {}
    progress = status.get("progress") or {}
    receipt = status.get("last_receipt") or {}
    receipt_summary = receipt.get("summary") or {}
    safe = bool(status.get("safe_to_remove"))
    eject_hint = ["ENTER = Eject", "SELECT = Next"]

    if state == "READY":
        return [
            [_head(status, "READY"), "Press COPY"],
            [
                _count_line(
                    "To USB",
                    int(summary.get("backup_files") or 0),
                    summary.get("backup_bytes"),
                ),
                _count_line(
                    "To NAS",
                    int(summary.get("ingest_files") or 0),
                    summary.get("ingest_bytes"),
                ),
            ],
            eject_hint,
        ]

    if state == "EXECUTING":
        total = int(progress.get("total_bytes") or 0)
        done = int(progress.get("done_bytes") or 0)
        percent = int(done * 100 / total) if total else 0
        files = int(progress.get("total_files") or 0)
        current_index = min(files, int(progress.get("done_files") or 0) + 1)
        current = str(progress.get("current") or "").rsplit("/", 1)[-1]
        return [
            [_fit(f"{_label(status)[:11]} {percent:>3}%"), progress_bar(percent)],
            [
                _fit(f"File {current_index}/{files}"),
                _fit(f"{format_bytes(done)}/{format_bytes(total)}"),
            ],
            [_fit(current or "Copying"), "Do not unplug"],
        ]

    if state == "COMPLETE":
        return [
            [_head(status, "DONE"), "Safe to remove" if safe else "Do not unplug"],
            [
                _fit(f"Copied {int(receipt_summary.get('copied_files') or 0)} files"),
                format_bytes(receipt_summary.get("copied_bytes")),
            ],
        ]

    if state in {"PARTIAL", "FAILED", "CANCELLED"}:
        failed = int(receipt_summary.get("failed_files") or 0)
        detail = (
            f"{failed} file(s) failed"
            if failed
            else _short_reason(status.get("reason"))
        )
        return [
            [_head(status, state), _fit(detail)],
            ["Safe to remove" if safe else "Do not unplug", "See TruePanel"],
        ]

    if state == "HOLD":
        conflicts = int(summary.get("conflicts") or 0)
        return [
            [_head(status, "HOLD"), _short_reason(status.get("reason"))],
            [
                _fit(f"Conflicts: {conflicts}") if conflicts else "Needs attention",
                "See TruePanel",
            ],
            eject_hint,
        ]

    if state == "CLEAR":
        return [[_fit(_label(status)), "In sync"], eject_hint]

    if state == "EJECTED":
        return [[_fit(_label(status)), "Safe to remove"]]

    if state == "UNREGISTERED":
        drives = status.get("unregistered") or [{}]
        first = drives[0]
        return [
            ["New drive found", _fit(first.get("label") or "")],
            ["Not registered", _fit(f"UUID {first.get('uuid') or '?'}")],
        ]

    return []


__all__ = [
    "loadmaster_enter_action",
    "loadmaster_pages",
    "loadmaster_takeover",
    "format_bytes",
]
