"""Host-owned Loadmaster controller: plug in a cartridge, press Copy, done.

The controller is the only place that connects Loadmaster's otherwise
independent pieces::

    dock scan --> read-only mount --> run plan --> arm Copy gate
        ^                                              |
        |            physical Copy press (GPIO75)  <---+
        |                       |
        +-- unmount <-- verified executor run (read-write remount)

Operator contract:

1. Plug in one registered cartridge. Within a few seconds it is identified,
   mounted read-only under ``mount_root``, and planned.
2. If the plan is ``READY`` the Copy button is armed for that exact plan
   digest. ``HOLD`` and ``CLEAR`` never arm.
3. Press Copy. The executor re-plans, refuses to run if anything changed,
   copies and verifies every file, records evidence and a receipt, then the
   cartridge is synced and unmounted (``safe_to_remove``).
4. Unplug. The same insertion is never run twice; replugging starts over.

The controller never deletes media, never runs without a physical press, and
treats every error as HOLD with a visible reason.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Any

from truepanel.cargo.backlog import LoadmasterBacklogError, load_backlog
from truepanel.cargo.cartridges import CartridgeDefinition, load_cartridge_registry
from truepanel.cargo.dock import CartridgeDock, DockedCartridge, LoadmasterDockError
from truepanel.cargo.executor import ExecutorSettings, RunContext, execute_run
from truepanel.cargo.loadmaster import LoadmasterPlanError, load_inventory
from truepanel.cargo.run_plan import build_run_plan, physical_preflight

LOGGER = logging.getLogger(__name__)

DEFAULT_POLL_SECONDS = 3.0
DEFAULT_REPLAN_SECONDS = 20.0


@dataclass(frozen=True)
class LoadmasterControllerSettings:
    registry_path: Path
    backlog_path: Path
    inventory_dir: Path
    receipts_dir: Path
    manifest_path: Path | None = None
    mount_root: Path = Path("/mnt/loadmaster")
    ingest_enabled: bool = True
    poll_seconds: float = DEFAULT_POLL_SECONDS
    replan_seconds: float = DEFAULT_REPLAN_SECONDS
    executor: ExecutorSettings = field(default_factory=ExecutorSettings)
    # Allow Mission Control (and the LCD's virtual buttons) to start a READY
    # run without the physical Copy press. Eject and refresh are always local.
    remote_confirmation: bool = False

    def inventory_path(self, cartridge_id: str) -> Path:
        return self.inventory_dir / f"{cartridge_id}.json"


class LoadmasterController:
    """Poll the dock, keep the Copy gate armed for READY plans, run on press."""

    def __init__(
        self,
        *,
        settings: LoadmasterControllerSettings,
        button: Any,
        dock_factory: Callable[[list[CartridgeDefinition]], CartridgeDock]
        | None = None,
        executor: Callable[[RunContext], dict[str, Any]] = execute_run,
        clock: Callable[[], float] = monotonic,
        run_in_thread: bool = True,
        event_recorder: Callable[[dict[str, object]], None] | None = None,
        status_publisher: Callable[[dict[str, Any]], None] | None = None,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings
        self.button = button
        self.dock_factory = dock_factory or (
            lambda cartridges: CartridgeDock(
                cartridges=cartridges, mount_root=settings.mount_root
            )
        )
        self.executor = executor
        self.clock = clock
        self.run_in_thread = bool(run_in_thread)
        self.event_recorder = event_recorder
        self.status_publisher = status_publisher
        self.wall_clock = wall_clock

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._run_stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._worker: threading.Thread | None = None

        self._state = "IDLE"
        self._reason: str | None = None
        self._cartridges: list[CartridgeDefinition] = []
        self._dock: CartridgeDock | None = None
        self._docked: DockedCartridge | None = None
        self._plan: dict[str, Any] | None = None
        self._planned_at: float | None = None
        self._armed_digest: str | None = None
        self._executing = False
        self._done_key: tuple[str, str, str] | None = None
        self._progress: dict[str, Any] | None = None
        self._last_receipt: dict[str, Any] | None = None
        self._safe_to_remove = False
        self._state_since = self.wall_clock()
        self._unregistered: list[dict[str, Any]] = []
        self._last_progress_publish = 0.0

    # ---------------------------------------------------------------- status

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            plan = self._plan
            return {
                "state": self._state,
                "reason": self._reason,
                "cartridge": self._docked.public_dict() if self._docked else None,
                "plan": (
                    {
                        "state": plan["state"],
                        "digest": plan["digest"],
                        "summary": plan["summary"],
                        "conflicts": plan["conflicts"][:20],
                        "notices": plan["notices"][:20],
                    }
                    if plan
                    else None
                ),
                "armed": self._armed_digest is not None,
                "executing": self._executing,
                "progress": dict(self._progress) if self._progress else None,
                "safe_to_remove": self._safe_to_remove,
                "last_receipt": self._last_receipt,
                "unregistered": list(self._unregistered),
                "remote_start_enabled": self.settings.remote_confirmation,
                "state_since": self._state_since,
                "updated_at": self.wall_clock(),
            }

    def _publish(self) -> None:
        if self.status_publisher is None:
            return
        try:
            self.status_publisher(self.snapshot())
        except Exception:
            LOGGER.exception("Could not publish Loadmaster status")

    def _record(self, event: dict[str, object]) -> None:
        if self.event_recorder is None:
            return
        try:
            self.event_recorder(dict(event))
        except Exception:
            LOGGER.exception("Could not record Loadmaster controller event")

    def _set(self, state: str, reason: str | None = None) -> None:
        if (state, reason) != (self._state, self._reason):
            self._record({"event": "state", "state": state, "reason": reason})
        if state != self._state:
            self._state_since = self.wall_clock()
        self._state = state
        self._reason = reason
        self._publish()

    def _disarm(self, reason: str) -> None:
        if self._armed_digest is not None:
            try:
                self.button.disarm(reason=reason)
            except Exception:
                LOGGER.exception("Loadmaster disarm failed")
        self._armed_digest = None

    def _hold(self, reason: str) -> None:
        self._disarm("hold")
        self._set("HOLD", reason)

    # ------------------------------------------------------------------ tick

    def tick(self) -> None:
        """Advance the state machine once. Safe to call repeatedly."""

        with self._lock:
            self._tick()
            self._publish()

    def _tick(self) -> None:
        if self._executing:
            return

        try:
            self._cartridges = load_cartridge_registry(self.settings.registry_path)
            self._dock = self.dock_factory(self._cartridges)
            scan = self._dock.scan()
        except (ValueError, OSError, LoadmasterDockError) as error:
            self._hold(f"DOCK_UNAVAILABLE: {error}")
            return

        if scan.state == "EMPTY":
            if self._docked is not None:
                self._record({"event": "undocked", **self._docked.public_dict()})
                try:
                    self._dock.release_orphan(self._docked.cartridge.cartridge_id)
                except LoadmasterDockError:
                    LOGGER.exception("Loadmaster orphan release failed")
            self._disarm("undocked")
            self._docked = None
            self._plan = None
            self._done_key = None
            self._safe_to_remove = False
            self._progress = None
            self._unregistered = [
                {
                    "label": device.label,
                    "uuid": device.uuid,
                    "serial": device.serial,
                    "fstype": device.fstype,
                    "device": device.path,
                }
                for device in scan.unregistered_labeled
            ]
            if self._unregistered:
                first = self._unregistered[0]
                self._set(
                    "UNREGISTERED",
                    f"drive '{first['label']}' UUID {first['uuid']} is not "
                    "in the cartridge registry",
                )
            else:
                self._set("IDLE")
            return

        if scan.state == "MULTIPLE":
            self._docked = None
            self._plan = None
            self._hold("MULTIPLE_CARTRIDGES: dock one cartridge at a time")
            return

        docked = scan.docked[0]
        self._unregistered = []

        if self._docked is None or self._docked.key != docked.key:
            self._disarm("new insertion")
            self._plan = None
            self._planned_at = None
            self._safe_to_remove = False
            self._progress = None
            self._record({"event": "docked", **docked.public_dict()})
        self._docked = docked

        if self._done_key == docked.key:
            # This insertion already ran; wait for unplug.
            return

        if not docked.identity_verified:
            self._plan = None
            self._hold(f"IDENTITY_UNVERIFIED: {docked.identity_reason}")
            return

        now = self.clock()
        stale = (
            self._plan is None
            or self._planned_at is None
            or now - self._planned_at >= self.settings.replan_seconds
        )
        if stale:
            self._plan_and_arm(docked, now)

    def _plan_and_arm(self, docked: DockedCartridge, now: float) -> None:
        cartridge = docked.cartridge
        assert self._dock is not None

        try:
            mount = self._dock.mount_read_only(docked)
        except LoadmasterDockError as error:
            self._plan = None
            self._hold(f"MOUNT_FAILED: {error}")
            return

        inventory_path = self.settings.inventory_path(cartridge.cartridge_id)
        if not inventory_path.exists():
            self._plan = None
            self._hold(
                "NOT_COMMISSIONED: no inventory baseline for "
                f"{cartridge.cartridge_id}; run commissioning first"
            )
            return

        try:
            backlog = load_backlog(self.settings.backlog_path)
            inventory = load_inventory(
                inventory_path, cartridge_id=cartridge.cartridge_id
            )
            plan = build_run_plan(
                cartridge=cartridge,
                cartridges=self._cartridges,
                usb_mount=mount,
                backlog=backlog,
                inventory=inventory,
                ingest_enabled=self.settings.ingest_enabled,
                tolerance_seconds=self.settings.executor.tolerance_seconds,
            )
        except (
            LoadmasterBacklogError,
            LoadmasterPlanError,
            OSError,
            ValueError,
        ) as error:
            self._plan = None
            self._hold(f"PLAN_FAILED: {error}")
            return

        self._plan = plan
        self._planned_at = now

        if plan["state"] == "HOLD":
            self._hold(f"PLAN_HOLD: {plan['summary']['conflicts']} conflict(s)")
            return

        if plan["state"] == "CLEAR":
            self._disarm("clear")
            self._set("CLEAR", "cartridge is already in sync")
            return

        preflight = physical_preflight(
            plan=plan,
            cartridge=cartridge,
            device_serial=docked.device.serial,
            identity_verified=docked.identity_verified,
            baseline_verified=True,
            backlog_verified=True,
            generated_at_monotonic=self.clock(),
        )
        try:
            self.button.arm(preflight)
        except (ValueError, RuntimeError) as error:
            self._armed_digest = None
            self._set("HOLD", f"ARM_FAILED: {error}")
            return

        self._armed_digest = plan["digest"]
        self._set("READY", "press Copy to transfer")

    # --------------------------------------------------------- confirmation

    def on_confirmation(self, confirmation: Any) -> None:
        """Called by the Copy-button service after one accepted press."""

        result = self._begin_run(
            plan_digest=getattr(confirmation, "plan_digest", None),
            cartridge_id=getattr(confirmation, "cartridge_id", None),
            source="copy_button",
        )
        if not result["ok"]:
            self._record(
                {
                    "event": "confirmation_ignored",
                    "plan_digest": getattr(confirmation, "plan_digest", None),
                    "status": result["status"],
                }
            )

    # -------------------------------------------------------------- commands

    def request_start(self, *, plan_digest: str, source: str) -> dict[str, Any]:
        """Start a READY run without the physical press (remote/LCD)."""

        if not self.settings.remote_confirmation:
            return _result(
                False,
                "remote_disabled",
                "Remote start is disabled; press Copy on the NAS.",
            )
        with self._lock:
            cartridge_id = self._docked.cartridge.cartridge_id if self._docked else None
        return self._begin_run(
            plan_digest=plan_digest, cartridge_id=cartridge_id, source=source
        )

    def request_eject(self, *, source: str) -> dict[str, Any]:
        """Flush and unmount the docked cartridge without transferring."""

        with self._lock:
            if self._executing:
                return _result(False, "busy", "A transfer is running.")
            docked, dock = self._docked, self._dock
            if docked is None or dock is None:
                return _result(False, "not_docked", "No cartridge is docked.")
            self._disarm("eject")
            try:
                dock.release(docked)
            except Exception as error:  # noqa: BLE001
                LOGGER.exception("Loadmaster eject failed")
                self._set("HOLD", f"EJECT_FAILED: {error}")
                return _result(False, "eject_failed", str(error))
            self._done_key = docked.key
            self._plan = None
            self._safe_to_remove = True
            self._record({"event": "ejected", "source": source})
            self._set("EJECTED", "safe to remove")
            return _result(True, "ejected", "Cartridge unmounted; safe to remove.")

    def request_refresh(self, *, source: str) -> dict[str, Any]:
        """Re-plan now, including a cartridge that already ran or was ejected."""

        with self._lock:
            if self._executing:
                return _result(False, "busy", "A transfer is running.")
            self._done_key = None
            self._plan = None
            self._planned_at = None
            self._safe_to_remove = False
            self._record({"event": "refresh", "source": source})
        self.tick()
        with self._lock:
            return _result(True, "refreshed", self._state)

    def _begin_run(
        self,
        *,
        plan_digest: Any,
        cartridge_id: Any,
        source: str,
    ) -> dict[str, Any]:
        with self._lock:
            docked = self._docked
            plan = self._plan
            dock = self._dock

            if self._executing:
                return _result(False, "busy", "A transfer is already running.")
            if docked is None or plan is None or dock is None:
                return _result(False, "not_ready", "No cartridge is ready.")
            if plan["state"] != "READY" or self._state != "READY":
                return _result(False, "not_ready", f"Loadmaster is {self._state}.")
            if plan_digest != plan["digest"]:
                return _result(
                    False,
                    "plan_changed",
                    "The plan changed; review it again before starting.",
                )
            if cartridge_id != docked.cartridge.cartridge_id:
                return _result(False, "wrong_cartridge", "Cartridge changed.")

            self._executing = True
            self._disarm("executing")
            self._run_stop.clear()
            self._progress = {
                "done_files": 0,
                "total_files": len(plan["actions"]),
                "done_bytes": 0,
                "total_bytes": int(plan["summary"]["backup_bytes"])
                + int(plan["summary"]["ingest_bytes"]),
                "current": None,
            }
            self._record({"event": "run_started", "source": source})
            self._set("EXECUTING", f"copying {len(plan['actions'])} file(s)")
            digest = plan["digest"]

        if self.run_in_thread:
            self._worker = threading.Thread(
                target=self._run_confirmed,
                args=(dock, docked, digest),
                name="truepanel-loadmaster-executor",
                daemon=True,
            )
            self._worker.start()
        else:
            self._run_confirmed(dock, docked, digest)
        return _result(True, "started", "Transfer started.", source=source)

    def _progress_update(self, progress: dict[str, Any]) -> None:
        with self._lock:
            self._progress = progress
            now = self.clock()
            if now - self._last_progress_publish >= 1.0:
                self._last_progress_publish = now
                self._publish()

    def _run_confirmed(
        self,
        dock: CartridgeDock,
        docked: DockedCartridge,
        digest: str,
    ) -> None:
        cartridge = docked.cartridge
        receipt: dict[str, Any] | None = None
        failure: str | None = None

        try:
            mount = dock.remount_read_write(docked)
            context = RunContext(
                cartridge=cartridge,
                cartridges=list(self._cartridges),
                usb_mount=mount,
                backlog=load_backlog(self.settings.backlog_path),
                inventory=load_inventory(
                    self.settings.inventory_path(cartridge.cartridge_id),
                    cartridge_id=cartridge.cartridge_id,
                ),
                inventory_path=self.settings.inventory_path(cartridge.cartridge_id),
                expected_digest=digest,
                ingest_enabled=self.settings.ingest_enabled,
                receipts_dir=self.settings.receipts_dir,
                manifest_path=self.settings.manifest_path,
                settings=self.settings.executor,
                stop_event=self._run_stop,
                progress=self._progress_update,
            )
            receipt = self.executor(context)
        except Exception as error:  # noqa: BLE001 - every failure must surface
            LOGGER.exception("Loadmaster run failed")
            failure = f"{type(error).__name__}: {error}"

        released = True
        try:
            dock.release(docked)
        except Exception:
            LOGGER.exception("Loadmaster release failed")
            released = False

        with self._lock:
            self._executing = False
            self._done_key = docked.key
            self._plan = None
            self._safe_to_remove = released
            if receipt is not None:
                self._last_receipt = {
                    "run_id": receipt.get("run_id"),
                    "state": receipt.get("state"),
                    "reason": receipt.get("reason"),
                    "summary": receipt.get("summary"),
                    "receipt_path": receipt.get("receipt_path"),
                }
                state = str(receipt.get("state") or "FAILED")
                reason = receipt.get("reason")
            else:
                state, reason = "FAILED", failure
            if not released:
                reason = f"{reason or ''} (unmount failed; do not unplug)".strip()
            elif state == "COMPLETE":
                reason = "safe to remove"
            self._set(state, reason)
            self._record({"event": "run_finished", "state": state, "reason": reason})

    # ------------------------------------------------------------- lifecycle

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop, name="truepanel-loadmaster-controller", daemon=True
            )
            self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                LOGGER.exception("Loadmaster controller tick failed")
                with self._lock:
                    self._hold("CONTROLLER_ERROR")
            self._stop.wait(self.settings.poll_seconds)

    def stop(self) -> None:
        self._stop.set()
        self._run_stop.set()
        thread, worker = self._thread, self._worker
        for item in (thread, worker):
            if item is not None and item is not threading.current_thread():
                item.join(timeout=30)
        with self._lock:
            self._disarm("shutdown")
            self._thread = None


def _result(ok: bool, status: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": ok, "status": status, "message": message, **extra}


def _path(value: Any) -> Path | None:
    text = str(value or "").strip()
    return Path(text) if text else None


def _owner(value: Any) -> tuple[int, int] | None:
    text = str(value or "").strip()
    if not text:
        return None
    uid, _, gid = text.partition(":")
    return int(uid), int(gid or uid)


def settings_from_config(config: dict[str, Any]) -> LoadmasterControllerSettings | None:
    """Return controller settings when execution is explicitly enabled."""

    mission = config.get("mission_control") or {}
    cargo = mission.get("cargo_bay") or {}
    loadmaster = cargo.get("loadmaster") or {}
    execution = loadmaster.get("execution") or {}

    if loadmaster.get("enabled") is not True or execution.get("enabled") is not True:
        return None

    registry = _path(loadmaster.get("cartridge_registry_path"))
    backlog = _path(loadmaster.get("backlog_path"))
    inventory_dir = _path(execution.get("inventory_dir"))
    receipts_dir = _path(execution.get("receipts_dir"))

    missing = [
        name
        for name, value in (
            ("cartridge_registry_path", registry),
            ("backlog_path", backlog),
            ("execution.inventory_dir", inventory_dir),
            ("execution.receipts_dir", receipts_dir),
        )
        if value is None
    ]
    if missing:
        raise ValueError(f"Loadmaster execution is missing: {', '.join(missing)}")

    backup = cargo.get("backup") or {}

    return LoadmasterControllerSettings(
        registry_path=registry,
        backlog_path=backlog,
        inventory_dir=inventory_dir,
        receipts_dir=receipts_dir,
        manifest_path=_path(backup.get("manifest_path")),
        mount_root=_path(execution.get("mount_root")) or Path("/mnt/loadmaster"),
        ingest_enabled=execution.get("ingest_enabled", True) is not False,
        poll_seconds=float(execution.get("poll_seconds") or DEFAULT_POLL_SECONDS),
        replan_seconds=float(execution.get("replan_seconds") or DEFAULT_REPLAN_SECONDS),
        executor=ExecutorSettings(
            verify=str(execution.get("verify") or "sha256"),
            ingest_owner=_owner(execution.get("ingest_owner")),
        ),
        remote_confirmation=execution.get("remote_confirmation") is True,
    )


__all__ = [
    "LoadmasterController",
    "LoadmasterControllerSettings",
    "settings_from_config",
]
