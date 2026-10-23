#!/usr/bin/env python3
"""TV N-Z independent guardian host-namespace qualification. NEVER mounts RW.

Default is read-only preflight. --ro-test launches a short-lived independent
systemd guard with a synthetic sleeping owner, verifies a live fresh status in
the host mount namespace, stops the synthetic owner and confirms RO recovery.
It does not read/copy media, arm a physical button, or enter a writable window.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys
import time
from pathlib import Path

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.independent_ro_watchdog import (
    owner_start_ticks, verify_independent_guard,
)
from truepanel.cargo.tv_nz_ro_watchdog import TvNzPin, mount_mode, preflight

STAGE = Path("/mnt/SSDs/Applications/TruePanel-Executor-Stage")
STATE = Path("/mnt/SSDs/Applications/Loadmaster-Watchdog-Qualification")
JOURNAL = STATE / "tv-nz-ro-qualification"
PYTHON = "/usr/bin/python3"


def _root_private(path: Path) -> None:
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
            or info.st_mode & 0o077 or path.is_symlink()):
        raise BackupExecutionError("TV N-Z qualification journal must be root-only")


def build_guard_command(*, unit: str, owner: int, ticks: int,
                        digest: str, nonce: str, status: Path) -> list[str]:
    return [
        "systemd-run", "--unit=" + unit,
        "--property=WorkingDirectory=" + str(STAGE),
        "--property=PrivateMounts=no", "--property=NoNewPrivileges=yes",
        "--property=Restart=no",
        PYTHON, "-m", "tools.loadmaster_tv_nz_ro_guard",
        "--watch", "--owner-pid", str(owner),
        "--owner-start-ticks", str(ticks),
        "--plan-digest", digest, "--attempt-nonce", nonce,
        "--unit", unit, "--status-file", str(status),
        "--lease-seconds", "55",
    ]


def qualify_read_only_guard() -> dict:
    if os.geteuid() != 0:
        raise BackupExecutionError("root required for systemd guard qualification")
    if not STAGE.is_dir() or STAGE.is_symlink():
        raise BackupExecutionError("development checkout unavailable")
    _root_private(STATE)
    preflight()
    if not JOURNAL.exists():
        JOURNAL.mkdir(mode=0o700)
    _root_private(JOURNAL)
    nonce = secrets.token_hex(16)
    digest = hashlib.sha256(("TV_NZ_RO_ONLY_GUARD_" + nonce).encode()).hexdigest()
    unit = "loadmaster-ro-guard-" + nonce[:12] + ".service"
    status = JOURNAL / (nonce + ".json")
    if status.exists() or status.is_symlink():
        raise BackupExecutionError("qualification state collision")
    owner = subprocess.Popen(
        ["sleep", "60"], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ticks = owner_start_ticks(owner.pid)
        command = build_guard_command(
            unit=unit, owner=owner.pid, ticks=ticks,
            digest=digest, nonce=nonce, status=status)
        subprocess.run(command, check=True, timeout=12,
                       capture_output=True, text=True)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if verify_independent_guard(
                    path=status, plan_digest=digest,
                    attempt_nonce=nonce, owner_pid=owner.pid,
                    owner_ticks=ticks, unit=unit):
                break
            time.sleep(.12)
        else:
            raise BackupExecutionError("independent TV N-Z guard never READY")
        if mount_mode(TvNzPin()) != "ro":
            raise BackupExecutionError("TV N-Z unexpectedly changed mount mode")
        owner.terminate()
        owner.wait(timeout=5)
        finish = time.monotonic() + 20
        while time.monotonic() < finish:
            try:
                state = json.loads(status.read_text()).get("state")
            except (OSError, ValueError):
                state = None
            if state == "RESTORED_RO":
                break
            time.sleep(.12)
        else:
            raise BackupExecutionError("TV N-Z guard did not report RO restoration")
        final = subprocess.check_output([
            "systemctl", "show", unit,
            "--property=Result,ExecMainStatus,ActiveState"], text=True, timeout=8)
        fields = dict(line.split("=", 1) for line in final.splitlines() if "=" in line)
        if (fields.get("Result") != "success" or
                fields.get("ExecMainStatus") != "0" or
                fields.get("ActiveState") == "active"):
            raise BackupExecutionError("TV N-Z watchdog service exit unverified")
        if mount_mode(TvNzPin()) != "ro":
            raise BackupExecutionError("TV N-Z cartridge not RO postqualification")
        return {
            "state": "TV_NZ_HOST_NAMESPACE_RO_GUARD_QUALIFIED",
            "serial": TvNzPin().serial, "uuid": TvNzPin().uuid,
            "mount_mode": "ro",
            "guard_verified": True, "rescue_needed": False,
            "usb_writable": False, "usb_written": False,
            "gpio_armed": False,
        }
    finally:
        if owner.poll() is None:
            owner.terminate()
            try:
                owner.wait(timeout=4)
            except subprocess.TimeoutExpired:
                owner.kill()
                owner.wait(timeout=4)
        # Intentionally do NOT stop guard if it is still running:
        # owner termination activates guard RO restoration.


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ro-test", action="store_true")
    args = parser.parse_args(argv)
    outcome = qualify_read_only_guard() if args.ro_test else preflight()
    print(json.dumps(outcome, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("TV_NZ_QUALIFICATION_HOLD:", type(exc).__name__, str(exc),
              file=sys.stderr, flush=True)
        sys.exit(2)
