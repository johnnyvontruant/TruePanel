#!/usr/bin/env python3
"""Seed Checkpoint 11 source on SSD only, without touching the cartridge.

Explicit --prepare-ssd-only required. Existing destination is never modified.
An already prepared matching source is safe to recheck, not replaced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

from truepanel.cargo.backup_executor import BackupExecutionError
from tools.loadmaster_spare_bidirectional_live_fire import NAS, USB, EXPORT, INGEST
from tools.loadmaster_spare_bidirectional_preview import pinned_spare_identity

# Content is intentionally unique to this acceptance case and deterministic.
PAYLOAD = ((b'LOADMASTER CHECKPOINT11 NAS OUTBOUND TEST 2026-10-23\n' * 512)
           + b'END-OF-CHECKPOINT11-OUTBOUND\n')


def _safe_parent(p: Path) -> None:
    if not p.is_relative_to(NAS) or any(x.is_symlink() for x in (p, *p.parents)):
        raise BackupExecutionError('unsafe SSD acceptance path')


def prepare(*, write_ssd: bool) -> dict:
    if os.geteuid() != 0:
        raise BackupExecutionError('root required for pinned spare attestation')
    if pinned_spare_identity()[2] is not True:
        raise BackupExecutionError('USB spare must be mounted read-only')
    ingest_src = USB / INGEST[1]
    ingest_dest = NAS / INGEST[1]
    export_dst = USB / EXPORT[1]
    export_src = NAS / EXPORT[1]
    if not ingest_src.is_file() or any(x.is_symlink() for x in (ingest_src, *ingest_src.parents)):
        raise BackupExecutionError('selected USB synthetic ingest source missing/unsafe')
    for path in (export_dst, ingest_dest, export_src):
        if path.is_symlink():
            raise BackupExecutionError('symlinked acceptance file')
    if os.path.lexists(export_dst) or os.path.lexists(ingest_dest):
        raise BackupExecutionError('one of the acceptance destinations is already occupied')
    if not write_ssd:
        return {'state':'SSD_PREPARE_DRY_RUN', 'usb_written': False,
                'nas_file_exists': export_src.is_file(),
                'selected_ingest': str(ingest_src), 'selected_export': str(export_src)}
    if NAS.exists() and (NAS.is_symlink() or not NAS.is_dir()):
        raise BackupExecutionError('invalid SSD acceptance root')
    _safe_parent(export_src)
    NAS.mkdir(mode=0o700, parents=False, exist_ok=True)
    export_src.parent.mkdir(mode=0o700, exist_ok=True)
    if os.path.lexists(export_src):
        fd = os.open(export_src, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            actual = hashlib.sha256()
            while b := os.read(fd, 8192):
                actual.update(b)
        finally:
            os.close(fd)
        if actual.digest() != hashlib.sha256(PAYLOAD).digest():
            raise BackupExecutionError('existing SSD source differs, never overwrite')
    else:
        fd = os.open(export_src, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as f:
            f.write(PAYLOAD)
            f.flush()
            os.fsync(f.fileno())
        fd = os.open(export_src.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return {'state':'CHECKPOINT11_SSD_ONLY_PREPARED', 'usb_written': False,
            'export_source': str(export_src), 'export_bytes': len(PAYLOAD),
            'export_sha256': hashlib.sha256(PAYLOAD).hexdigest(),
            'ingest_source': str(ingest_src)}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepare-ssd-only', action='store_true')
    args=p.parse_args(argv)
    try:
        print(json.dumps(prepare(write_ssd=args.prepare_ssd_only),indent=2), flush=True)
        return 0
    except Exception as e:
        print('CHECKPOINT11_PREPARE_HOLD:', type(e).__name__, str(e), file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
