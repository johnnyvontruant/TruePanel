#!/usr/bin/env python3
"""Inspect Loadmaster's registered pending queue without touching any media.

Default is all registered cartridges, up to five REVIEW rows per cartridge.
No source hashing, mount operations, Copy-button use, rsync or state changes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from truepanel.cargo.backlog import load_backlog, LoadmasterBacklogError
from truepanel.cargo.cartridges import load_cartridge_registry
from truepanel.cargo.queue_preview import (
    preview_cartridge_queue, QueuePreviewError, MAX_ROWS_PER_CARTRIDGE,
)

REGISTRY = Path("/var/lib/truepanel/loadmaster/cartridges.json")
BACKLOG = Path("/var/lib/truepanel/loadmaster/pending-cargo.json")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cartridge-id", default=None)
    parser.add_argument("--max-rows", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        cartridges = load_cartridge_registry(REGISTRY)
        backlog = load_backlog(BACKLOG)
        report = preview_cartridge_queue(
            cartridges=cartridges, backlog=backlog,
            cartridge_id=args.cartridge_id, row_limit=args.max_rows)
    except (QueuePreviewError, LoadmasterBacklogError,
            ValueError, OSError, TypeError) as exc:
        print("LOADMASTER_QUEUE_PREVIEW_HOLD:", str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
