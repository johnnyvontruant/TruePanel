#!/usr/bin/env python3
"""Single attended Checkpoint 25: tests, queue, verified receipt, SSD flightdeck.

No writes to USB or HDD, no GPIO and no transfer executor invoked. If the
operator supplies --activate-ui, make only one backed-up application YAML
change and restart Mission Control, with fail-closed rollback.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from truepanel.cargo.backlog import load_backlog
from truepanel.cargo.cartridges import load_cartridge_registry
from truepanel.cargo.production_receipt_reconcile import compare_verified_receipt
from truepanel.cargo.production_flightdeck_activate import activate, ActivationHold
from truepanel.cargo.queue_preview import preview_cartridge_queue
from truepanel.cargo.tv_nz_ro_watchdog import preflight, TV_NZ_TEST_RELATIVE
from truepanel.cargo.tv_nz_supervised_export import (
    MANIFEST, EXPECTED_FILE, EXPECTED_BYTES, EXPECTED_SHA256,
)
from truepanel.cargo.backup_manifest import validate_backup_manifest
from truepanel.cargo.flightdeck import read_flightdeck
from tools.loadmaster_queue_preview import REGISTRY, BACKLOG
from tools.loadmaster_tv_nz_production_flightdeck import (
    build_current_tv_nz_snapshot, publish_private_ssd, OUTPUT,
)

STAGE = Path("/mnt/SSDs/Applications/TruePanel-Executor-Stage")
TESTS = (
    "test_loadmaster_production_receipt_reconcile.py",
    "test_loadmaster_flightdeck_activation.py",
    "test_loadmaster_queue_preview.py",
    "test_loadmaster_production_flightdeck.py",
    "test_loadmaster_production_interrupt_lab.py",
    "test_loadmaster_tv_nz_supervised_export.py",
    "test_loadmaster_tv_nz_supervised_runner.py",
    "test_supervised_bidirectional_batch.py",
)


def _service_active(unit: str) -> bool:
    p = subprocess.run(["systemctl", "is-active", unit],
                       capture_output=True, text=True, timeout=8)
    return p.returncode == 0 and p.stdout.strip() == "active"


def finish(*, activate_ui: bool) -> dict:
    if os.geteuid() != 0:
        raise ActivationHold("root required")
    if not STAGE.is_dir() or STAGE.is_symlink():
        raise ActivationHold("expected staging checkout missing")
    if not _service_active("truepanel.service"):
        raise ActivationHold("production TruePanel unexpectedly unavailable")
    if not _service_active("truepanel-mission-control.service"):
        raise ActivationHold("production Mission Control unexpectedly unavailable")

    print("=== CONSOLIDATED SAFETY REGRESSIONS ===", flush=True)
    for pattern in TESTS:
        print("TEST", pattern, flush=True)
        result = subprocess.run([
            sys.executable, "-m", "unittest", "discover", "-s", "tests",
            "-p", pattern, "-q"], cwd=STAGE, timeout=100)
        if result.returncode:
            raise ActivationHold("Linux regression failure: " + pattern)

    print("=== LIVE DEVICE READ-ONLY VERIFICATION ===", flush=True)
    identity = preflight()
    print(json.dumps(identity, indent=2), flush=True)

    print("=== REGISTERED CARGO QUEUE (LEDGER ONLY) ===", flush=True)
    backlog = load_backlog(BACKLOG)
    registry = load_cartridge_registry(REGISTRY)
    queue = preview_cartridge_queue(
        cartridges=registry, backlog=backlog,
        cartridge_id="tv-n-z", row_limit=3)
    if len(queue["cartridges"]) != 1:
        raise ActivationHold("TV N-Z queue mapping missing")
    group = queue["cartridges"][0]
    if group["backup_policy_enabled"] or group["ingest_policy_enabled"]:
        raise ActivationHold("TV N-Z physical permission unexpectedly enabled")
    print(json.dumps({
        "state": queue["state"], "pending_items": group["pending_items"],
        "pending_bytes": group["pending_bytes"],
        "excluded_protected": group["excluded_protected"],
        "unsupported_paths": group["unsupported_paths"],
        "read_only": True, "transfer_enabled": False,
        "first_three_review_rows": group["rows"],
    }, indent=2), flush=True)

    print("=== INDEPENDENT LIVE RECEIPT RECONCILIATION ===", flush=True)
    verified_snapshot = build_current_tv_nz_snapshot()
    receipt = validate_backup_manifest(MANIFEST)
    comparison = compare_verified_receipt(
        backlog=backlog, manifest=receipt,
        file_path=EXPECTED_FILE, relative_path=TV_NZ_TEST_RELATIVE,
        size_bytes=EXPECTED_BYTES, sha256=EXPECTED_SHA256,
        independently_verified_snapshot=verified_snapshot)
    print(json.dumps(comparison, indent=2), flush=True)

    print("=== PUBLISH SAFE SSD-ONLY FLIGHT DECK ===", flush=True)
    publish_private_ssd(verified_snapshot)
    if read_flightdeck(OUTPUT).get("state") != "READY":
        raise ActivationHold("published Mission Control snapshot invalid")
    preflight()  # final exact physical identity check after SSD publication

    ui = activate(apply=activate_ui)
    print("=== UI CONFIGURATION ===", flush=True)
    print(json.dumps(ui, indent=2), flush=True)

    if not _service_active("truepanel.service") or not _service_active(
            "truepanel-mission-control.service"):
        raise ActivationHold("production service not active after qualification")

    return {
        "state": "LOADMASTER_SPRINT_CHECKPOINT25_COMPLETE",
        "linux_test_suites_passed": len(TESTS),
        "live_backup_receipts_verified": verified_snapshot["receipts"]["backup"],
        "tv_nz_pending_ledger_entries": group["pending_items"],
        "tv_nz_pending_ledger_bytes": group["pending_bytes"],
        "pilot_receipt_status": comparison["pilot_status"],
        "ui_state": ui["state"],
        "flightdeck_file": str(OUTPUT),
        "usb_mount": "ro",
        "usb_written": False,
        "hdd_written": False,
        "backup_ledger_modified": False,
        "physical_authorized": False,
        "production_services_active": True,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--activate-ui", action="store_true",
        help="Back up and connect the existing read-only Mission Control display")
    args = parser.parse_args(argv)
    try:
        result = finish(activate_ui=args.activate_ui)
    except BaseException as exc:
        # Fail closed. A failed UI change performs its own rollback; USB
        # recovery is NOT needed because this procedure never remounts USB.
        print("LOADMASTER_SPRINT_HOLD:", type(exc).__name__, str(exc),
              file=sys.stderr, flush=True)
        return 2
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
