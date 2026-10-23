#!/usr/bin/env python3
"""ONE verified TV N-Z backup against the pending ledger, purely read-only.

Before calling the read-only ledger comparison, reattest TV N-Z and rehash
both exact media files plus the root-private SSD production backup manifest.
Does NOT write the durable queue, backup evidence or a Mission Control config.
"""
from __future__ import annotations

import json
import sys

from truepanel.cargo.backlog import load_backlog, LoadmasterBacklogError
from truepanel.cargo.backup_manifest import validate_backup_manifest
from truepanel.cargo.production_receipt_reconcile import (
    compare_verified_receipt, ReceiptReconcileError,
)
from truepanel.cargo.tv_nz_supervised_export import (
    EXPECTED_FILE, EXPECTED_BYTES, EXPECTED_SHA256,
    MANIFEST,
)
from truepanel.cargo.tv_nz_ro_watchdog import TV_NZ_TEST_RELATIVE
from tools.loadmaster_queue_preview import BACKLOG
from tools.loadmaster_tv_nz_production_flightdeck import build_current_tv_nz_snapshot


def main(argv=None) -> int:
    if argv:
        print("TV_NZ_RECONCILIATION_HOLD: no mutation or execution flags supported",
              file=sys.stderr)
        return 2
    try:
        snapshot = build_current_tv_nz_snapshot()
        # No cached Flight Deck report can authorize accounting. Current
        # source and USB hashes were measured in this process, read-only.
        manifest = validate_backup_manifest(MANIFEST)
        ledger = load_backlog(BACKLOG)
        comparison = compare_verified_receipt(
            backlog=ledger, manifest=manifest,
            file_path=EXPECTED_FILE,
            relative_path=TV_NZ_TEST_RELATIVE,
            size_bytes=EXPECTED_BYTES, sha256=EXPECTED_SHA256,
            independently_verified_snapshot=snapshot)
        print(json.dumps(comparison, indent=2, sort_keys=True))
        return 0
    except (LoadmasterBacklogError, ReceiptReconcileError,
            ValueError, TypeError, OSError) as exc:
        print("TV_NZ_RECONCILIATION_HOLD:", str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
