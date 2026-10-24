"""The Loadmaster service: one state machine for plug in -> plan -> press -> sync.

States the operator sees (LCD and TruePanel):

``IDLE``      no drive plugged in
``CHECKING``  a drive was found; it is mounted read-only and compared
``READY``     there is work; press Copy (or Start in TruePanel)
``CONFIRM``   there is work including many removals; confirm in TruePanel
``CLEAR``     the drive is already in sync
``HOLD``      something needs a person (reason given)
``NEW_DRIVE`` a drive with a known name but a different ID; Adopt in TruePanel
``COPYING``   transfer in progress
``DONE`` / ``PARTIAL`` / ``FAILED`` / ``STOPPED``  run finished; drive unmounted
``EJECTED``   unmounted on request without a transfer

Slow work (scanning, copying) happens on one worker thread so the dock poll,
the Copy button and the command socket always stay responsive.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from typing import Any

from .config import Settings
from .dock import Dock, Docked, DockError
from .link import CommandServer, publish_status, reply
from .plan import build_plan, pending_to_usb
from .run import RunContext, execute
from .scan import ScanError, scan
from .state import DriveRecord, StateStore

LOGGER = logging.getLogger(__name__)

FINISHED = frozenset({"DONE", "PARTIAL", "FAILED", "STOPPED", "EJECTED"})
EJECTABLE = frozenset({"READY", "CONFIRM", "CLEAR", "HOLD", "NEW_DRIVE"})
REPLAN_SECONDS = 120.0
RUN_STATE = {
    "COMPLETE": "DONE",
    "PARTIAL": "PARTIAL",
    "FAILED": "FAILED",
    "CANCELLED": "STOPPED",
}


class ButtonWatcher:
    """Debounced edge detection for the active-low GPIO75 Copy button."""

    def __init__(
        self,
        read_level: Callable[[], int],
        on_press: Callable[[], None],
        *,
        debounce: float = 0.06,
        interval: float = 0.02,
    ) -> None:
        self.read_level = read_level
        self.on_press = on_press
        self.debounce = debounce
        self.interval = interval
        self.error: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="loadmaster-button", daemon=True
        )
        self._thread.start()

    def _run(self) -> None:
        pressed = False
        candidate, since = False, time.monotonic()
        while not self._stop.wait(self.interval):
            try:
                now_pressed = self.read_level() == 0
            except Exception as error:  # noqa: BLE001
                self.error = f"Copy button unreadable: {error}"
                LOGGER.exception("Loadmaster Copy button failed")
                return
            now = time.monotonic()
            if now_pressed != candidate:
                candidate, since = now_pressed, now
            elif candidate != pressed and now - since >= self.debounce:
                pressed = candidate
                if pressed:
                    try:
                        self.on_press()
                    except Exception:  # noqa: BLE001
                        LOGGER.exception("Loadmaster Copy press handling failed")

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)


class LoadmasterService:
    def __init__(
        self,
        settings: Settings,
        *,
        dock: Dock | None = None,
        store: StateStore | None = None,
        servarr_poll: Callable[[], dict[str, str]] | None = None,
        button_reader: Any = None,
        button_note: str | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings
        self.dock = dock or Dock(settings.drives, settings.mount_root)
        self.store = store or StateStore(settings.state_dir)
        self.servarr_poll = servarr_poll
        self.clock = clock

        self._lock = threading.RLock()
        self._jobs: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._stop = threading.Event()
        self._run_stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._server: CommandServer | None = None

        self.state = "IDLE"
        self.message = "Plug in a Loadmaster drive."
        self.state_since = clock()
        self.docked: Docked | None = None
        self.record: DriveRecord | None = None
        self.plan: dict[str, Any] | None = None
        self.planned_at = 0.0
        self.progress: dict[str, Any] | None = None
        self.last_run: dict[str, Any] | None = None
        self.finished_insertion: tuple | None = None
        self.drive_summaries: list[dict[str, Any]] = []
        self.servarr_status: dict[str, str] = {}
        self.activity: list[dict[str, Any]] = self.store.recent_activity(30)
        self._last_publish = 0.0
        self._planning = False
        self._host_token_verifier = None

        self.button: ButtonWatcher | None = None
        self.button_note = button_note
        if button_reader is not None and button_note is None:
            self.button = ButtonWatcher(button_reader.read_level, self.press)

    # ------------------------------------------------------------ status

    def _set(self, state: str, message: str) -> None:
        if state != self.state:
            self.state_since = self.clock()
        self.state, self.message = state, message
        self.publish()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            plan = self.plan
            button = "off"
            if self.button is not None:
                button = self.button.error or "ready"
            elif self.button_note:
                button = self.button_note
            docked = None
            if self.docked is not None:
                docked = self.docked.public()
                docked["nas_path"] = str(self.docked.drive.nas_path)
                docked["usb_folder"] = self.docked.drive.usb_folder
                if self.record is not None:
                    docked["last_sync"] = self.record.last_sync
                    docked["first_sync"] = not self.record.known
            return {
                "state": self.state,
                "message": self.message,
                "state_since": self.state_since,
                "drive": docked,
                "plan": None
                if plan is None
                else {
                    "digest": plan["digest"],
                    "state": plan["state"],
                    "first_sync": plan["first_sync"],
                    "needs_confirmation": plan["needs_confirmation"],
                    "summary": plan["summary"],
                    "preview": plan["actions"][:40],
                    "conflicts": plan["conflicts"][:20],
                    "notices": plan["notices"][:20],
                },
                "progress": dict(self.progress) if self.progress else None,
                "last_run": self.last_run,
                "safe_to_remove": self.state in FINISHED,
                "drives": self.drive_summaries,
                "next_drive": next(
                    (d["name"] for d in self.drive_summaries if d.get("pending_files")),
                    None,
                ),
                "servarr": self.servarr_status,
                "button": button,
                "remote_start": self.settings.remote_start,
                "activity": self.activity,
            }

    def publish(self, *, throttle: bool = False) -> None:
        now = time.monotonic()
        if throttle and now - self._last_publish < 1.0:
            return
        self._last_publish = now
        try:
            publish_status(self.settings.status_path, self.snapshot())
        except OSError:
            LOGGER.exception("Could not publish Loadmaster status")

    # -------------------------------------------------------------- dock

    def tick(self) -> None:
        """Poll USB once and react to plug-in / unplug."""

        with self._lock:
            if self.state == "COPYING":
                return
            try:
                found = self.dock.scan()
            except DockError as error:
                self._set("HOLD", f"Cannot list USB drives: {error}")
                return

            if not found:
                if self.docked is not None:
                    try:
                        self.dock.release_vanished(self.docked.drive.key)
                    except DockError:
                        LOGGER.exception("Loadmaster lazy unmount failed")
                    self.store.log("unplugged", drive=self.docked.drive.name)
                self.docked = self.record = self.plan = self.progress = None
                self.finished_insertion = None
                if self.state != "IDLE":
                    self._set("IDLE", "Plug in a Loadmaster drive.")
                return

            if len(found) > 1:
                names = ", ".join(d.drive.name for d in found)
                self.docked = self.plan = None
                self._set("HOLD", f"Plug in one drive at a time ({names}).")
                return

            docked = found[0]
            if self.docked is None or self.docked.insertion != docked.insertion:
                self.docked = docked
                self.plan = None
                self.finished_insertion = None
                self.store.log(
                    "plugged_in", drive=docked.drive.name, device=docked.device.path
                )
                self._queue_plan()
                return

            if self.finished_insertion == docked.insertion or self._planning:
                return
            if (
                self.state in {"READY", "CONFIRM", "CLEAR"}
                and self.clock() - self.planned_at > REPLAN_SECONDS
            ):
                self._queue_plan(quiet=True)

    def _queue_plan(self, *, quiet: bool = False) -> None:
        self._planning = True
        if not quiet:
            self._set("CHECKING", f"Checking {self.docked.drive.name}…")
        self._jobs.put(("plan", self.docked))

    # ---------------------------------------------------------- planning

    def _make_plan(self, docked: Docked) -> dict[str, Any] | None:
        """Mount read-only, compare, and return the plan (or set HOLD)."""

        drive = docked.drive
        record = self.store.load_record(drive.key, drive.name)
        if record.uuid and record.uuid != docked.device.uuid:
            with self._lock:
                self.record = record
                self._set(
                    "NEW_DRIVE",
                    f"This {drive.name} drive is not the one Loadmaster knows. "
                    "Adopt it in TruePanel to treat it as a fresh copy.",
                )
            return None
        if record.uuid is None:
            record.uuid, record.serial = docked.device.uuid, docked.device.serial
            self.store.save_record(drive.key, record)

        mount = self.dock.mount_ro(docked)
        usb_root = drive.usb_root(mount)
        if not usb_root.is_dir():
            raise ScanError(
                f'Folder "{drive.usb_folder}" is not on the drive. If the files sit '
                'at the top of the drive, set usb_folder: "" for it in truepanel.yaml.'
            )
        nas = scan(drive.nas_path)
        usb = scan(usb_root)
        plan = build_plan(
            drive_name=drive.name,
            nas=nas.files,
            usb=usb.files,
            record=record.files if record.known else None,
            usb_fstype=docked.device.fstype,
            large_delete_files=self.settings.large_delete_files,
        )
        with self._lock:
            self.record = record
        return plan

    def _job_plan(self, docked: Docked) -> None:
        try:
            plan = self._make_plan(docked)
        except (DockError, ScanError, OSError, ValueError) as error:
            with self._lock:
                self._planning = False
                if self.docked is docked:
                    self.plan = None
                    self._set("HOLD", str(error))
            return
        with self._lock:
            self._planning = False
            if self.docked is docked and plan is not None and self.state != "COPYING":
                self._apply_plan(docked, plan)

    def _apply_plan(self, docked: Docked, plan: dict[str, Any], note: str = "") -> None:
        self.plan, self.planned_at = plan, self.clock()
        summary = plan["summary"]
        if plan["state"] == "HOLD":
            self._set("HOLD", plan["reason"])
        elif plan["state"] == "CLEAR":
            self._set("CLEAR", note or f"{docked.drive.name} is up to date.")
        elif plan["needs_confirmation"]:
            removals = summary["delete_usb_files"] + summary["retire_nas_files"]
            self._set(
                "CONFIRM",
                note or f"{removals} files would be removed; confirm in TruePanel.",
            )
        else:
            self._set("READY", note or "Press Copy to sync.")

    # ------------------------------------------------------------ commands

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        action, source = request["action"], request["source"]
        if action == "start":
            # In acceptance mode only a verified host confirmation may start.
            # A socket caller can freely claim source="lcd" or "web".
            if (self.settings.extra.get("physical_acceptance_mode") is True
                    and source != "host"):
                return reply(False, "physical_only", "Acceptance requires physical host authorization.")
            if source == "host":
                if request.get("_host_authenticated") is not True:
                    return reply(False, "unauthorized", "Host authentication required.")
                if self.settings.extra.get("physical_bridge_enabled") is not True:
                    return reply(False, "bridge_disabled", "Physical bridge is not commissioned.")
                if (self.state != "READY" or not self.plan
                    or self.plan.get("needs_confirmation")
                    or self.plan["summary"].get("to_usb_files", 0) < 1
                    or any(self.plan["summary"].get(k, 0) for k in (
                        "to_nas_files", "delete_usb_files", "retire_nas_files", "conflicts"
                    ))):
                    return reply(False, "unsafe_plan", "Physical Copy requires outbound-only READY work.")
                # Require a single-use, short-lived credential tied to the
                # current cartridge and exact plan. Root peer UID alone does
                # not constitute proof of a physical confirmation.
                from pathlib import Path
                from .host_token import TokenVerifier, read_secret
                key_path = self.settings.extra.get("physical_token_key")
                if not key_path or self.docked is None:
                    return reply(False, "unauthorized", "Host token is not configured.")
                if self._host_token_verifier is None:
                    try:
                        self._host_token_verifier = TokenVerifier(
                            read_secret(Path(key_path)),
                            replay_db=self.settings.state_dir / "host-spent-tokens.sqlite3",
                        )
                    except (OSError, ValueError):
                        return reply(False, "unauthorized", "Invalid host token key.")
                # Revalidate the dock and digest before spending authority.
                # A previous status snapshot is not sufficient.
                with self._lock:
                    if self._planning or self.state != "READY" or not self.plan:
                        return reply(False, "not_ready", "Plan is no longer ready.")
                    if request["digest"] != self.plan["digest"]:
                        return reply(False, "plan_changed", "Plan digest changed.")
                    current = self.dock.scan()
                    if (
                        self.docked is None
                        or not any(
                            candidate.drive.key == self.docked.drive.key
                            and candidate.device.uuid == self.docked.device.uuid
                            and candidate.device.serial == self.docked.device.serial
                            and candidate.insertion == self.docked.insertion
                            for candidate in current
                        )
                    ):
                        return reply(False, "drive_changed", "Cartridge has changed.")
                    token = request.get("token")
                    if not isinstance(token, dict) or not self._host_token_verifier.consume(
                        request["digest"], self.docked.device.uuid,
                        self.docked.device.serial, token
                    ):
                        return reply(False, "unauthorized", "Invalid or consumed host token.")
                    return self.start(request["digest"], source="host", confirmed=False)
            if source != "lcd" and not self.settings.remote_start:
                return reply(
                    False,
                    "remote_disabled",
                    "Remote start is off; press Copy on the NAS.",
                )
            return self.start(
                request["digest"], source=source, confirmed=source == "web"
            )
        if action == "stop":
            return self.stop_run()
        if action == "eject":
            return self.eject(source)
        if action == "rescan":
            return self.rescan()
        return self.adopt()

    def press(self) -> None:
        if self.settings.extra.get("physical_acceptance_mode") is True:
            return  # Only the host-owned signed confirmation may start.
        with self._lock:
            if self.state == "READY" and self.plan:
                self.start(self.plan["digest"], source="copy_button", confirmed=False)
            elif self.state == "CONFIRM":
                self.message = "Many files would be removed; confirm in TruePanel."
                self.publish()

    def start(self, digest: str, *, source: str, confirmed: bool) -> dict[str, Any]:
        with self._lock:
            if self.state not in {"READY", "CONFIRM"} or not self.plan:
                return reply(False, "not_ready", f"Loadmaster is {self.state}.")
            if self._planning:
                return reply(
                    False, "busy", "Still checking the drive; try again shortly."
                )
            if digest != self.plan["digest"]:
                return reply(
                    False, "plan_changed", "The plan changed; review it again."
                )
            if self.state == "CONFIRM" and not confirmed:
                return reply(False, "confirmation_required", "Confirm in TruePanel.")
            self._run_stop.clear()
            self.progress = {
                "done_files": 0,
                "total_files": len(self.plan["actions"]),
                "done_bytes": 0,
                "total_bytes": 0,
                "current": None,
            }
            self._set("COPYING", "Checking nothing changed…")
            self._jobs.put(("run", (self.docked, digest, source)))
            return reply(True, "started", "Sync started.")

    def _job_run(self, docked: Docked, digest: str, source: str) -> None:
        receipt = None
        try:
            fresh = self._make_plan(docked)
            if fresh is None:
                return  # _make_plan already explained why (e.g. NEW_DRIVE)
            if fresh["digest"] != digest:
                with self._lock:
                    self.progress = None
                    self._apply_plan(
                        docked,
                        fresh,
                        "Something changed since the "
                        "plan was shown; check it and start again.",
                    )
                return
            mount = self.dock.mount_rw(docked)
            with self._lock:
                self._set("COPYING", "Copying…")
            receipt = execute(
                RunContext(
                    drive=docked.drive,
                    usb_root=docked.drive.usb_root(mount),
                    plan=fresh,
                    record=self.record,
                    store=self.store,
                    verify=self.settings.verify,
                    ingest_owner=self.settings.ingest_owner,
                    stop=self._run_stop,
                    progress=self._on_progress,
                    source=source,
                )
            )
        except (DockError, ScanError, OSError, ValueError) as error:
            LOGGER.exception("Loadmaster run failed")
            receipt = {"state": "FAILED", "reason": str(error), "summary": None}

        released = True
        try:
            self.dock.release(docked)
        except DockError:
            LOGGER.exception("Loadmaster unmount failed")
            released = False

        with self._lock:
            self.finished_insertion = docked.insertion
            self.plan = None
            self.last_run = {
                k: receipt.get(k)
                for k in ("id", "state", "reason", "summary", "finished")
            }
            self.activity = self.store.recent_activity(30)
            state = RUN_STATE.get(receipt["state"], "FAILED")
            message = receipt.get("reason") or "Sync complete."
            if not released:
                message += " Could not unmount: do not unplug yet."
            else:
                message += " Safe to remove."
            self._set(state, message)
        self._refresh_drive_summaries()

    def _on_progress(self, progress: dict[str, Any]) -> None:
        with self._lock:
            self.progress = progress
        self.publish(throttle=True)

    def stop_run(self) -> dict[str, Any]:
        if self.state != "COPYING":
            return reply(False, "not_running", "Nothing is copying.")
        self._run_stop.set()
        return reply(
            True,
            "stopping",
            "Stopping after the current block; "
            "finished files are kept and partial files resume next time.",
        )

    def eject(self, source: str) -> dict[str, Any]:
        with self._lock:
            if self.docked is None or self.state not in EJECTABLE | FINISHED:
                return reply(False, "not_ready", f"Cannot eject while {self.state}.")
            try:
                self.dock.release(self.docked)
            except DockError as error:
                return reply(False, "eject_failed", str(error))
            self.finished_insertion = self.docked.insertion
            self.plan = None
            self.store.log("ejected", drive=self.docked.drive.name, source=source)
            self._set("EJECTED", "Unmounted. Safe to remove.")
            return reply(True, "ejected", "Safe to remove.")

    def rescan(self) -> dict[str, Any]:
        with self._lock:
            if self.docked is None:
                return reply(False, "not_ready", "No drive is plugged in.")
            if self.state == "COPYING" or self._planning:
                return reply(False, "busy", "Busy; try again shortly.")
            self.finished_insertion = None
            self._queue_plan()
            return reply(True, "checking", "Checking the drive again.")

    def adopt(self) -> dict[str, Any]:
        with self._lock:
            if self.state != "NEW_DRIVE" or self.docked is None:
                return reply(False, "not_ready", "Nothing to adopt.")
            drive = self.docked.drive
            fresh = DriveRecord(
                name=drive.name,
                uuid=self.docked.device.uuid,
                serial=self.docked.device.serial,
            )
            self.store.save_record(drive.key, fresh)
            self.store.log("adopted", drive=drive.name, uuid=self.docked.device.uuid)
            self._queue_plan()
            return reply(True, "adopted", "Adopted; checking it as a first sync.")

    # --------------------------------------------------------- background

    def _refresh_drive_summaries(self) -> None:
        summaries = []
        for drive in self.settings.drives:
            entry = drive.public()
            try:
                record = self.store.load_record(drive.key, drive.name)
            except (OSError, ValueError):
                entry["error"] = "record unreadable"
                summaries.append(entry)
                continue
            entry["last_sync"] = record.last_sync
            if record.known:
                try:
                    files, size = pending_to_usb(
                        scan(drive.nas_path).files, record.files
                    )
                    entry.update(pending_files=files, pending_bytes=size)
                except ScanError as error:
                    entry["error"] = str(error)
            summaries.append(entry)
        summaries.sort(key=lambda d: -(d.get("pending_bytes") or 0))
        with self._lock:
            self.drive_summaries = summaries
        self.publish()

    def _background(self) -> None:
        next_servarr = next_pending = 0.0
        while not self._stop.wait(5):
            now = time.monotonic()
            if self.servarr_poll and now >= next_servarr:
                next_servarr = now + self.settings.servarr_poll_seconds
                status = self.servarr_poll()
                with self._lock:
                    self.servarr_status = status
                    self.activity = self.store.recent_activity(30)
                self.publish()
            if now >= next_pending and self.state != "COPYING":
                next_pending = now + self.settings.pending_scan_seconds
                self._refresh_drive_summaries()

    def _dispatch(self, kind: str, payload: Any) -> None:
        try:
            if kind == "plan":
                self._job_plan(payload)
            else:
                self._job_run(*payload)
        except Exception:  # noqa: BLE001 - keep the service alive
            LOGGER.exception("Loadmaster job failed")
            with self._lock:
                self._planning = False
                self.progress = None
                self._set("HOLD", "Internal error; see the TruePanel log.")

    def drain(self) -> None:
        """Run queued jobs on the calling thread (tests and the CLI)."""

        while True:
            try:
                kind, payload = self._jobs.get_nowait()
            except queue.Empty:
                return
            self._dispatch(kind, payload)

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                kind, payload = self._jobs.get(timeout=0.5)
            except queue.Empty:
                continue
            self._dispatch(kind, payload)

    def _dock_loop(self) -> None:
        while not self._stop.wait(self.settings.dock_poll_seconds):
            try:
                self.tick()
            except Exception:  # noqa: BLE001
                LOGGER.exception("Loadmaster dock poll failed")
            self.publish(throttle=True)

    # ---------------------------------------------------------- lifecycle

    def start_service(self) -> None:
        self._server = CommandServer(self.settings.command_socket, self.handle)
        self._server.start()
        for target, name in (
            (self._worker, "loadmaster-worker"),
            (self._dock_loop, "loadmaster-dock"),
            (self._background, "loadmaster-background"),
        ):
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self._threads.append(thread)
        if self.button is not None:
            self.button.start()
        self.store.log("service_started")
        self.tick()
        self.publish()

    def stop_service(self) -> None:
        self._stop.set()
        self._run_stop.set()
        if self.button is not None:
            self.button.stop()
        if self._server is not None:
            self._server.stop()
        for thread in self._threads:
            thread.join(timeout=30)


__all__ = ["ButtonWatcher", "LoadmasterService"]
