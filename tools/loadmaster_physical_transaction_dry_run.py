#!/usr/bin/env python3
"""Read-only transfer inspection. Never writes/remounts/arms hardware."""
import argparse
import json
from pathlib import Path
from truepanel.cargo.physical_transaction_dry_run import inspect_transaction

p = argparse.ArgumentParser()
for key in ('registry','backlog','mount','source'):
    p.add_argument('--'+key, type=Path, required=True)
p.add_argument('--cartridge-id', required=True)
p.add_argument('--by-id', required=True)
a = p.parse_args()
print(json.dumps(inspect_transaction(registry=a.registry, backlog=a.backlog,
    cartridge_id=a.cartridge_id, mount=a.mount, by_id=a.by_id,
    source_path=a.source), indent=2))
