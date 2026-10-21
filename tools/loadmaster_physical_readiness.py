#!/usr/bin/env python3
"""Read-only physical cartridge/episode readiness probe."""
import argparse
import json
from pathlib import Path
from truepanel.cargo.physical_readiness import probe_one_episode

p = argparse.ArgumentParser()
p.add_argument('--registry', type=Path, required=True)
p.add_argument('--backlog', type=Path, required=True)
p.add_argument('--cartridge-id', required=True)
p.add_argument('--mount', type=Path, required=True)
p.add_argument('--by-id', required=True)
p.add_argument('--source', type=Path, required=True)
a = p.parse_args()
print(json.dumps(probe_one_episode(registry=a.registry, backlog=a.backlog,
                                  cartridge_id=a.cartridge_id, mount=a.mount,
                                  by_id=a.by_id, source_path=a.source), indent=2))
