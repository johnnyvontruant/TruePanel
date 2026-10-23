#!/usr/bin/env python3
"""Current TV N-Z production receipt versus persistent backlog: NO mutation.

Checks exact mounted serial/UUID in RO mode; rehashes source AND USB, validates
private SSD receipt, reads pending ledger, and reports whether the first
physical backup *would be eligible* for future backlog reconciliation.
Never clears pending, publishes state, remounts or opens GPIO.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from truepanel.cargo.backlog import load_backlog
from truepanel.cargo.backup_manifest import validate_backup_manifest
from truepanel.cargo.production_receipt_reconcile import compare_verified_receipt
from truepanel.cargo.tv_nz_ro_watchdog import (
    TV_NZ_TEST_RELATIVE, TV_NZ_MOUNT, TvNzPin, mount_mode,
)
from truepanel.cargo.tv_nz_supervised_export import (
    MANIFEST, EXPECTED_FILE, EXPECTED_BYTES, EXPECTED_SHA256,
)
from tools.loadmaster_tv_nz_production_flightdeck import (
    build_current_tv_nz_snapshot,
)

BACKLOG = Path("/var/lib/truepanel/loadmaster/pending-cargo.json")


def audit_current_pilot() -> dict:
    if mount_mode(TvNzPin()) != "ro":
        raise ValueError("TV N-Z cartridge must be read-only")
    # This rehashes both verified production copies (not just a stale report).
    snapshot = build_current_tv_nz_snapshot()
    ledger = load_backlog(BACKLOG)
    verified_manifest = validate_backup_manifest(MANIFEST)
    outcome = compare_verified_receipt(
        backlog=ledger, manifest=verified_manifest,
        file_path=EXPECTED_FILE, relative_path=TV_NZ_TEST_RELATIVE,
        size_bytes=EXPECTED_BYTES, sha256=EXPECTED_SHA256,
        independently_verified_snapshot=snapshot)
    if mount_mode(TvNzPin()) != "ro":
        raise ValueError("TV N-Z mount changed during reconciliation preview")
    return outcome


def main() -> int:
    try:
        print(json.dumps(audit_current_pilot(), indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print("LOADMASTER_PRODUCTION_RECONCILE_HOLD:",
              type(exc).__name__, str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
