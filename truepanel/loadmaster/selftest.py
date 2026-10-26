"""Check Loadmaster on the real NAS: ``python3 -m truepanel.loadmaster selftest``.

Every v2 problem that only showed up on BattleStation (flat lsblk output, exFAT
renames, the Copy button, a plan that disagreed with the preview) was found by
hand. This runs those checks in one go and prints PASS / WARN / FAIL / SKIP.

By default it only reads, so it is safe while TruePanel runs. While the service
runs it owns the drive's mount and the Copy button, so the self-test asks the
service (its status) instead of touching either, and re-plans a docked drive
from the service's own read-only mount to prove both see the same plan.

``--hardware`` adds the checks that need the drive and the button to itself:
mount, remount read-write, a verified write and no-replace rename inside a
hidden scratch folder on the drive (removed again), and reading GPIO75. It
refuses to run while the service is running.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Settings
from .dock import Dock, Docked, DockError
from .identity import folder_keys, library_index
from .link import read_status
from .plan import build_plan
from .scan import ScanError, scan
from .state import StateStore
from .transfer import ItemError, _noreplace_rename

USB_FILESYSTEMS = frozenset({"exfat", "vfat", "ntfs", "ntfs3", "fuseblk"})
SCRATCH = ".loadmaster-selftest"


@dataclass
class Check:
    name: str
    result: str  # PASS, WARN, FAIL, SKIP
    detail: str


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, result: str, detail: str) -> None:
        self.checks.append(Check(name, result, detail))

    @property
    def failed(self) -> bool:
        return any(c.result == "FAIL" for c in self.checks)

    def lines(self) -> list[str]:
        return [f"{c.result:<4}  {c.name:<20} {c.detail}" for c in self.checks]


def run_selftest(
    settings: Settings,
    *,
    hardware: bool = False,
    dock: Any = None,
    status: Callable[[], dict[str, Any]] | None = None,
    usb_devices: Callable[[], list[Any]] | None = None,
    button_reader_factory: Callable[[], Any] | None = None,
    speaker: Callable[[], tuple[bool, str | None]] | None = None,
) -> Report:
    report = Report()
    dock = dock or Dock(settings.drives, settings.mount_root)
    store = StateStore(settings.state_dir)

    names = ", ".join(
        d.name + (f" (protected: {', '.join(d.protected)})" if d.protected else "")
        for d in settings.drives
    )
    report.add("config", "PASS", f"{len(settings.drives)} drives: {names}")

    _records(report, settings, store)
    library = _library(report, settings)
    docked = _detection(report, settings, dock, usb_devices)

    live = (status or (lambda: read_status(settings.status_path)))()
    running = bool(live.get("available"))
    _service(report, live, running)
    if running:
        _plan_agreement(report, settings, store, dock, docked, live, library)
    if speaker is not None:
        _speaker(report, settings, speaker)

    if hardware:
        if running:
            reason = "Loadmaster is running and owns the drive and the Copy button; stop TruePanel first"
            report.add("drive write test", "SKIP", reason)
            report.add("copy button", "SKIP", reason)
        else:
            _drive_write_test(report, dock, docked)
            _button(report, button_reader_factory)
    return report


# ------------------------------------------------------------------ checks


def _records(report: Report, settings: Settings, store: StateStore) -> None:
    never = []
    for drive in settings.drives:
        try:
            record = store.load_record(drive.key, drive.name)
        except (OSError, ValueError) as error:
            report.add("records", "FAIL", f"{drive.name}: record unreadable ({error})")
            return
        if not record.known:
            never.append(drive.name)
    if never:
        report.add("records", "WARN", f"never synced: {', '.join(never)}")
    else:
        report.add("records", "PASS", "every drive has a synced baseline")


def _library(report: Report, settings: Settings):
    started = time.monotonic()
    library = library_index((d.name, d.nas_path) for d in settings.drives)
    seconds = time.monotonic() - started
    shared = sum(1 for entries in library.values() if len(set(entries)) > 1)
    detail = f"{len(library)} identity keys in {seconds:.1f}s"
    if shared:
        report.add(
            "library",
            "WARN",
            f"{detail}; {shared} titles are in more than one NAS folder "
            "(a drive copy of them will be held)",
        )
    else:
        report.add("library", "PASS", detail)
    return library


def _detection(
    report: Report, settings: Settings, dock: Any, usb_devices
) -> list[Docked]:
    try:
        docked = dock.scan()
    except DockError as error:
        report.add("detection", "FAIL", f"could not list USB drives: {error}")
        return []
    found = ", ".join(
        f"{d.drive.name} on {d.device.path} ({d.device.uuid})" for d in docked
    )
    report.add("detection", "PASS", found or "no Loadmaster drive plugged in")

    if usb_devices is not None:
        names = {d.name.casefold() for d in settings.drives}
        strangers = [
            f"{d.label or '(no label)'} on {d.path}"
            for d in usb_devices()
            if d.usb
            and d.fstype in USB_FILESYSTEMS
            and d.label.casefold() not in names
            and d.label not in {"EFI", "boot-pool"}
        ]
        if strangers:
            report.add(
                "unknown USB drives",
                "WARN",
                f"{', '.join(strangers)}: label must match a drive name to be synced",
            )
    return docked


def _service(report: Report, live: dict[str, Any], running: bool) -> None:
    if not running:
        report.add(
            "service", "WARN", live.get("message") or "Loadmaster is not running"
        )
        return
    report.add("service", "PASS", f"{live.get('state')}: {live.get('message')}")

    button = live.get("button") or "off"
    report.add(
        "copy button",
        "PASS" if button == "ready" else "FAIL" if "unreadable" in button else "WARN",
        f"service reports {button}",
    )
    servarr = live.get("servarr") or {}
    bad = {k: v for k, v in servarr.items() if v != "ok"}
    if not servarr:
        report.add("sonarr/radarr", "WARN", "not configured")
    elif bad:
        report.add(
            "sonarr/radarr", "FAIL", ", ".join(f"{k}: {v}" for k, v in bad.items())
        )
    else:
        report.add("sonarr/radarr", "PASS", ", ".join(f"{k} ok" for k in servarr))


def _plan_agreement(report, settings, store, dock, docked, live, library) -> None:
    """Re-plan the docked drive from the service's read-only mount."""

    plan = live.get("plan") or {}
    drive_name = (live.get("drive") or {}).get("name")
    match = next((d for d in docked if d.drive.name == drive_name), None)
    if match is None or not plan.get("digest"):
        report.add("plan agreement", "SKIP", "no planned drive plugged in")
        return
    if dock.mount_state(match) not in {"RO", "RW"}:
        report.add(
            "plan agreement", "SKIP", f"{drive_name} is not mounted by Loadmaster"
        )
        return
    drive = match.drive
    usb_root = drive.usb_root(dock.mountpoint(match))
    try:
        record = store.load_record(drive.key, drive.name)
        mine = build_plan(
            drive_name=drive.name,
            nas=scan(drive.nas_path).files,
            usb=scan(usb_root).files,
            record=record.files if record.known else None,
            usb_fstype=match.device.fstype,
            large_delete_files=settings.large_delete_files,
            protected=drive.protected,
            library=library,
            usb_folders=folder_keys(usb_root),
        )
    except (ScanError, OSError, ValueError) as error:
        report.add("plan agreement", "FAIL", f"could not re-plan {drive.name}: {error}")
        return
    if mine["digest"] == plan["digest"]:
        report.add(
            "plan agreement", "PASS", f"{drive.name}: self-test and service plan match"
        )
    else:
        report.add(
            "plan agreement",
            "WARN",
            f"{drive.name}: plans differ (something changed since it was planned?); "
            "press Rescan and run the self-test again",
        )


def _speaker(report: Report, settings: Settings, speaker) -> None:
    enabled, device = speaker()
    if not settings.sounds.get("enabled"):
        report.add("speaker", "SKIP", "Loadmaster tones are off (loadmaster.sounds)")
    elif not enabled:
        report.add(
            "speaker",
            "WARN",
            "tones are on but buzzer.enabled is false, so they are silent",
        )
    elif device is None:
        report.add(
            "speaker", "WARN", "no PC speaker device found; tones will be silent"
        )
    else:
        quiet = settings.sounds.get("quiet_hours")
        note = ""
        if quiet:
            note = f"; quiet {quiet[0] // 60:02}:{quiet[0] % 60:02}-{quiet[1] // 60:02}:{quiet[1] % 60:02}"
        report.add(
            "speaker",
            "PASS",
            f"{device}{note} (try: python3 -m truepanel.loadmaster sound done)",
        )


def _drive_write_test(report: Report, dock: Any, docked: list[Docked]) -> None:
    if not docked:
        report.add("drive write test", "SKIP", "no Loadmaster drive plugged in")
        return
    target = docked[0]
    scratch: Path | None = None
    try:
        mount = dock.mount_ro(target)
        usb_root = target.drive.usb_root(mount)
        scan(usb_root)
        dock.mount_rw(target)
        scratch = usb_root / SCRATCH
        scratch.mkdir(exist_ok=True)
        payload = os.urandom(1 << 20)
        partial = scratch / ".partial"
        with open(partial, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        final = scratch / "published.bin"
        _noreplace_rename(partial, final)
        if (
            hashlib.sha256(final.read_bytes()).digest()
            != hashlib.sha256(payload).digest()
        ):
            raise ItemError("READ_BACK_MISMATCH", str(final))
        (scratch / ".second").write_bytes(b"x")
        try:
            _noreplace_rename(scratch / ".second", final)
        except ItemError:
            pass
        else:
            raise ItemError("RENAME_REPLACED_A_FILE", str(final))
        report.add(
            "drive write test",
            "PASS",
            f"{target.drive.name} ({target.device.fstype}): mount ro/rw, 1 MB verified write, "
            "no-replace rename refused an existing name",
        )
    except (DockError, ScanError, ItemError, OSError) as error:
        report.add("drive write test", "FAIL", f"{target.drive.name}: {error}")
    finally:
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)
        try:
            dock.release(target)
        except DockError as error:
            report.add("drive release", "FAIL", f"{target.drive.name}: {error}")


def _button(report: Report, reader_factory) -> None:
    if reader_factory is None:
        from truepanel.hardware.fintek_gpio import FintekCopyButtonReader

        reader_factory = FintekCopyButtonReader
    try:
        reader = reader_factory()
    except Exception as error:  # noqa: BLE001 - any probe failure is the result
        report.add("copy button", "FAIL", f"Fintek GPIO75 not readable: {error}")
        return
    try:
        levels = set()
        stop = threading.Event()
        for _ in range(20):
            levels.add(reader.read_level())
            stop.wait(0.05)
    finally:
        close = getattr(reader, "close", None)
        if close:
            close()
    state = "pressed" if levels == {0} else "released" if levels == {1} else "changing"
    report.add("copy button", "PASS", f"GPIO75 readable; {state} during the test")


__all__ = ["Check", "Report", "run_selftest"]
