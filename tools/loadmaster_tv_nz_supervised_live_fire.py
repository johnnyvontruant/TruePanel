#!/usr/bin/env python3
"""Attended TV N-Z one-episode production pilot, gated OFF by default.

Without flags this program ONLY hashes/reinspects the HDD file and checks the
read-only USB. --live-fire requires separately stated operator presence and
degraded-pool risk acceptance, exclusive GPIO ownership, *real* Copy-button
press, two independent RO recovery services and a fresh physical action digest.
No USB->NAS ingest, deletes, overwrites or unrestricted batch execution.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.bidirectional_host_scope import (
    CargoScope, HostBidirectionalApprovalSession, inspect_bidirectional,
)
from truepanel.cargo.copy_button import DEFAULT_CONFIRMATION_WINDOW_SECONDS
from truepanel.cargo.independent_ro_watchdog import (
    owner_start_ticks, verify_independent_guard,
)
from truepanel.cargo.supervised_mount import SupervisedWriteWindow
from truepanel.cargo.tv_nz_ro_watchdog import (
    TvNzPin, mount_mode, TV_NZ_MOUNT, TV_NZ_BY_ID,
    TV_NZ_UUID, TV_NZ_SERIAL, TV_NZ_LIBRARY, TV_NZ_CARTRIDGE_ROOT,
    TV_NZ_TEST_RELATIVE,
)
from truepanel.cargo.tv_nz_supervised_export import (
    STATE, EVIDENCE, MANIFEST, execute_one_export, _root_only,
)
from truepanel.hardware.fintek_gpio import FintekCopyButtonReader
from truepanel.host.loadmaster_copy_button import LoadmasterCopyButtonService
from truepanel.host.loadmaster_session_bridge import LoadmasterHostSessionBridge
from truepanel.host.ownership import HostOwnershipGuard
from tools.loadmaster_tv_nz_hdd_export_scope import qualify_read_only

STAGE = Path("/mnt/SSDs/Applications/TruePanel-Executor-Stage")
GUARD_LEASE_SECONDS = 150
RESCUE_TIMER_SECONDS = 175


def _call(args: list[str], *, timeout: int = 12) -> str:
    return subprocess.check_output(
        args, text=True, stderr=subprocess.STDOUT, timeout=timeout).strip()


def _service_active(unit: str) -> bool:
    result = subprocess.run(
        ["systemctl", "is-active", unit],
        capture_output=True, text=True, timeout=8, check=False)
    return result.returncode == 0 and result.stdout.strip() == "active"


def _unit_fields(unit: str) -> dict[str, str]:
    info = _call(["systemctl", "show", unit,
                  "--property=ActiveState,LoadState"])
    return dict(line.split("=", 1) for line in info.splitlines()
                if "=" in line)


def pinned_identity() -> tuple[str, str, bool]:
    return (TV_NZ_UUID, TV_NZ_SERIAL, mount_mode(TvNzPin()) == "ro")


def _fresh_actions():
    return inspect_bidirectional(
        nas_root=TV_NZ_LIBRARY, usb_root=TV_NZ_CARTRIDGE_ROOT,
        entries=(("NAS_TO_USB", TV_NZ_TEST_RELATIVE),),
        recover_verified=False)


def _scope() -> CargoScope:
    evidence = qualify_read_only()
    if evidence["state"] != "TV_NZ_HDD_EXPORT_SCOPE_READ_ONLY_PASS":
        raise BackupExecutionError("real HDD source/cart not qualified")
    return CargoScope("tv-n-z", TV_NZ_UUID, TV_NZ_SERIAL, _fresh_actions())


def _guard_and_rescue(scope: CargoScope):
    """Start exact TV N-Z watchdog and separately scheduled RO rescue, not RW."""
    _root_only(STATE)
    _root_only(EVIDENCE)
    if mount_mode(TvNzPin()) != "ro":
        raise BackupExecutionError("cannot arm rescue from a writable cartridge")
    nonce = scope.attempt_nonce
    unit = "loadmaster-ro-guard-" + nonce[:12] + ".service"
    rescue = "loadmaster-tv-nz-ro-rescue-" + nonce[:12]
    status = EVIDENCE / (nonce + ".json")
    if status.exists() or status.is_symlink():
        raise BackupExecutionError("TV N-Z watchdog status collision")
    owner_pid = os.getpid()
    ticks = owner_start_ticks(owner_pid)
    _call([
        "systemd-run", "--unit=" + unit,
        "--property=WorkingDirectory=" + str(STAGE),
        "--property=Restart=no",
        "--property=PrivateMounts=no",
        "--property=NoNewPrivileges=yes",
        "/usr/bin/python3", "-m", "tools.loadmaster_tv_nz_ro_guard",
        "--watch", "--owner-pid", str(owner_pid),
        "--owner-start-ticks", str(ticks),
        "--plan-digest", scope.digest, "--attempt-nonce", nonce,
        "--unit", unit, "--status-file", str(status),
        "--lease-seconds", str(GUARD_LEASE_SECONDS),
    ])

    def watchdog_verified() -> bool:
        return verify_independent_guard(
            path=status, plan_digest=scope.digest,
            attempt_nonce=nonce, owner_pid=owner_pid,
            owner_ticks=ticks, unit=unit)

    deadline = time.monotonic() + 12
    while not watchdog_verified():
        if time.monotonic() >= deadline:
            raise BackupExecutionError("TV N-Z independent watchdog did not become READY")
        time.sleep(.12)

    _call([
        "systemd-run", "--unit=" + rescue,
        "--on-active=" + str(RESCUE_TIMER_SECONDS) + "s",
        "--timer-property=AccuracySec=1s",
        "--property=WorkingDirectory=" + str(STAGE),
        "--property=PrivateMounts=no",
        "--property=NoNewPrivileges=yes",
        "/usr/bin/python3", "-m", "tools.loadmaster_tv_nz_ro_guard",
        "--rescue",
    ])

    def rescue_verified() -> bool:
        try:
            state = _unit_fields(rescue + ".timer")
        except (OSError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired):
            return False
        return (state.get("LoadState") == "loaded"
                and state.get("ActiveState") == "active")

    if not rescue_verified() or not watchdog_verified():
        raise BackupExecutionError("independent TV N-Z rescue/watcher not armed")
    if mount_mode(TvNzPin()) != "ro":
        raise BackupExecutionError("TV N-Z mode changed after rescue arm")
    return watchdog_verified, rescue_verified


def execute(*, live: bool = False, operator_present: bool = False,
            accept_degraded_pool: bool = False) -> int:
    scope = _scope()
    print(json.dumps({
        "state": "TV_NZ_ONE_FILE_READ_ONLY_READY",
        "source": str(TV_NZ_LIBRARY / TV_NZ_TEST_RELATIVE),
        "usb": str(TV_NZ_CARTRIDGE_ROOT / TV_NZ_TEST_RELATIVE),
        "scope_digest": scope.digest,
        "size_bytes": scope.actions[0].size_bytes,
        "sha256": scope.actions[0].sha256,
        "physical_authorized": False,
        "live_fire_requested": live,
        "gpio_armed": False,
        "usb_written": False,
    }, indent=2), flush=True)
    if not live:
        return 0
    if not operator_present or not accept_degraded_pool:
        raise BackupExecutionError(
            "live fire requires operator-present and degraded-pool risk flags")
    if os.geteuid() != 0 or not STAGE.is_dir():
        raise BackupExecutionError("root in staged BattleStation checkout required")
    if _service_active("truepanel.service"):
        raise BackupExecutionError(
            "GPIO already occupied: production truepanel.service must be safely stopped")
    if not _service_active("truepanel-mission-control.service"):
        raise BackupExecutionError("Mission Control must remain active")
    if not MANIFEST.is_relative_to(EVIDENCE):
        raise BackupExecutionError("evidence manifest outside private SSD state")
    _root_only(STATE)
    _root_only(EVIDENCE)

    ownership = HostOwnershipGuard("loadmaster-tv-nz-hdd-export-operator")
    ownership.acquire()
    reader = service = bridge = None
    try:
        # Only the actual Fintek button event can confirm this session.
        reader = FintekCopyButtonReader()
        service = LoadmasterCopyButtonService(reader=reader)
        session = HostBidirectionalApprovalSession(
            fresh_actions=_fresh_actions, attest_identity=pinned_identity)
        bridge = LoadmasterHostSessionBridge(service=service, session=session)
        service.start()
        armed = bridge.prepare_and_arm((scope, EVIDENCE))
        if (armed.get("plan_digest") != scope.digest
                or armed.get("backup_files") != 1):
            raise BackupExecutionError("GPIO armed action not exactly one episode")
        print("ARMED: PRESS LOWER COPY BUTTON ONCE (30 second limit)", flush=True)
        until = time.monotonic() + DEFAULT_CONFIRMATION_WINDOW_SECONDS - 2
        while not bridge.confirmed:
            if time.monotonic() >= until:
                raise BackupExecutionError("physical Copy confirmation expired")
            if service.snapshot().get("last_error"):
                raise BackupExecutionError("physical GPIO reader failed")
            time.sleep(.05)

        print("CONFIRMED: starting two independent RO recovery protections",
              flush=True)
        watcher, rescue = _guard_and_rescue(scope)
        result = execute_one_export(
            scope=scope, bridge=bridge,
            writable_session=SupervisedWriteWindow(
                mount=TV_NZ_MOUNT, by_id=TV_NZ_BY_ID, uuid=TV_NZ_UUID),
            watchdog_verified=watcher,
            rescue_timer_verified=rescue,
            manifest=MANIFEST)
        if mount_mode(TvNzPin()) != "ro":
            raise BackupExecutionError("CRITICAL: TV N-Z not read-only post-transfer")
        print(json.dumps(result, indent=2), flush=True)
        print("FINAL_TV_NZ_HDD_EXPORT_PASS", flush=True)
        return 0
    finally:
        if bridge is not None:
            bridge.disarm()
        if service is not None:
            service.stop()
        if reader is not None:
            reader.close()
        ownership.release()
        # Independent guard/timer MUST NOT be stopped here while USB is RW
        # or unknown. Owner exit must activate RO recovery.


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-fire", action="store_true")
    parser.add_argument("--operator-present", action="store_true")
    parser.add_argument("--accept-degraded-pool", action="store_true")
    args = parser.parse_args(argv)
    try:
        return execute(
            live=args.live_fire, operator_present=args.operator_present,
            accept_degraded_pool=args.accept_degraded_pool)
    except Exception as exc:
        print("TV_NZ_HDD_EXPORT_HOLD:", type(exc).__name__, str(exc),
              file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
