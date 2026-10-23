#!/usr/bin/env python3
"""Independent physical TV N-Z RO watchdog. It never remounts RW.

--preflight: readonly device identity inspection
--watch: supervised systemd service for an operator-owned live window
--rescue: independent RO-only timer, exact cartridge identity required

No program in this module can start a transfer or authorize GPIO.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.independent_ro_watchdog import (
    owner_start_ticks, same_host_mount_namespace, write_status,
)
from truepanel.cargo.tv_nz_ro_watchdog import (
    TvNzPin, guard_loop, mount_mode, preflight, restore_ro,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight", action="store_true")
    modes.add_argument("--watch", action="store_true")
    modes.add_argument("--rescue", action="store_true")
    parser.add_argument("--owner-pid", type=int)
    parser.add_argument("--owner-start-ticks", type=int)
    parser.add_argument("--plan-digest")
    parser.add_argument("--attempt-nonce")
    parser.add_argument("--unit")
    parser.add_argument("--status-file", type=Path)
    parser.add_argument("--lease-seconds", type=int, default=90)
    args = parser.parse_args(argv)
    if args.preflight:
        print(json.dumps(preflight(), indent=2))
        return 0

    if os.geteuid() != 0 or not same_host_mount_namespace(os.getpid()):
        raise BackupExecutionError("TV N-Z watchdog needs root in the host mount namespace")

    if args.rescue:
        print(json.dumps({
            "state": restore_ro(),
            "uuid": TvNzPin().uuid,
            "mount": str(TvNzPin().mount),
            "usb_written": False,
            "remount_rw_attempted": False,
        }, indent=2))
        return 0

    if (args.owner_pid is None or args.owner_start_ticks is None
            or not re.fullmatch(r"[a-f0-9]{64}", args.plan_digest or "")
            or not re.fullmatch(r"[a-f0-9]{32}", args.attempt_nonce or "")
            or args.unit != f"loadmaster-ro-guard-{args.attempt_nonce[:12]}.service"
            or args.status_file is None
            or not 5 <= args.lease_seconds <= 180
            or args.owner_pid == os.getpid()):
        raise BackupExecutionError("invalid exact TV N-Z watchdog launch")
    if owner_start_ticks(args.owner_pid) != args.owner_start_ticks:
        raise BackupExecutionError("TV N-Z watchdog owner PID was reused")
    pin = TvNzPin()
    if mount_mode(pin) != "ro":
        raise BackupExecutionError("TV N-Z watchdog requires starting RO")
    started = time.monotonic()
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()

    def report(state: str) -> None:
        write_status(args.status_file, {
            "state": state, "unit": args.unit,
            "plan_digest": args.plan_digest,
            "attempt_nonce": args.attempt_nonce,
            "owner_pid": args.owner_pid,
            "owner_ticks": args.owner_start_ticks,
            "guardian_pid": os.getpid(),
            "monotonic_at": time.monotonic(),
            "boot_id": boot_id,
            "cartridge": "tv-n-z",
            "cartridge_uuid": pin.uuid,
            "cartridge_serial": pin.serial,
        })

    try:
        guard_loop(
            pin=pin, owner_pid=args.owner_pid,
            owner_ticks=args.owner_start_ticks,
            deadline=started + args.lease_seconds, report=report,
        )
    except BaseException:
        # If identity is swapped/missing, do not touch any other USB drive.
        try:
            state = restore_ro(pin)
            report("FAILED_BUT_RO" if state == "RESTORED_RO"
                   else "CRITICAL_NOT_RO")
        except BaseException:
            try:
                report("CRITICAL_RO_UNVERIFIED")
            except BaseException:
                pass
        raise
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"TV_NZ_RO_GUARD_HOLD: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        sys.exit(2)
