#!/usr/bin/env python3
"""One-shot, supervised Loadmaster acceptance on BattleStation.

Never runs unless invoked explicitly with both live-fire flags.
Requires exclusive Host hardware lock, mounted cartridge RO at start, and
real Copy-button confirmation. Nothing deploys this tool automatically.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from truepanel.cargo.backup_executor import BackupExecutionError
from truepanel.cargo.cartridges import load_cartridge_registry
from truepanel.cargo.loadmaster import build_backlog_backup_plan
from truepanel.cargo.physical_session import ReadOnlyHostSession, PhysicalSessionSpec
from truepanel.cargo.physical_transaction_dry_run import inspect_transaction
from truepanel.cargo.physical_backup_actuator import execute_supervised_single_file
from truepanel.cargo.supervised_mount import SupervisedWriteWindow
from truepanel.hardware.fintek_gpio import FintekCopyButtonReader
from truepanel.host.loadmaster_copy_button import LoadmasterCopyButtonService
from truepanel.host.loadmaster_session_bridge import LoadmasterHostSessionBridge
from truepanel.host.ownership import HostOwnershipGuard


def main() -> int:
    parser = argparse.ArgumentParser(description='Supervised one-episode Loadmaster live fire')
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--backlog', type=Path, required=True)
    parser.add_argument('--mount', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--by-id', required=True)
    parser.add_argument('--cartridge-id', required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--journal-root', type=Path, required=True)
    parser.add_argument('--live-fire', action='store_true')
    parser.add_argument('--operator-present', action='store_true')
    args = parser.parse_args()

    inspection = inspect_transaction(
        registry=args.registry, backlog=args.backlog,
        cartridge_id=args.cartridge_id, mount=args.mount,
        by_id=args.by_id, source_path=args.source)
    print(json.dumps(inspection, indent=2), flush=True)

    if not args.live_fire:
        print('PREVIEW_COMPLETE: no hardware accessed or modified', flush=True)
        return 0
    if not args.operator_present:
        parser.error('--live-fire requires --operator-present')

    cands = [c for c in load_cartridge_registry(args.registry)
             if c.cartridge_id == args.cartridge_id]
    if len(cands) != 1:
        raise BackupExecutionError('registered cartridge not unique')
    cart = cands[0]
    items = [i for i in json.loads(args.backlog.read_text())['items']
             if i.get('current_path') == str(args.source)]
    if len(items) != 1:
        raise BackupExecutionError('single backlog item required')
    plan = build_backlog_backup_plan(
        cartridge=cart, usb_mount=args.mount, backlog_items=items)
    from truepanel.cargo.backup_coordinator import canonical_plan_digest
    if canonical_plan_digest(plan) != inspection['plan_digest']:
        raise BackupExecutionError('plan changed since inspection')

    # The production Host Agent must be stopped deliberately by the operator
    # before this exclusive lease can be acquired. The tool never stops it.
    owner = HostOwnershipGuard('loadmaster-supervised-live-fire')
    owner.acquire()
    service = None
    bridge = None
    try:
        args.journal_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if args.journal_root.is_symlink():
            raise BackupExecutionError('journal root symlink prohibited')
        if args.journal_root.stat().st_mode & 0o022:
            raise BackupExecutionError('journal root permissions unsafe')
        reader = FintekCopyButtonReader()
        service = LoadmasterCopyButtonService(reader=reader)
        bridge = LoadmasterHostSessionBridge(
            service=service, session=ReadOnlyHostSession())
        spec = PhysicalSessionSpec(
            registry=args.registry, backlog=args.backlog,
            cartridge_id=args.cartridge_id, mount=args.mount,
            by_id=args.by_id, source_path=args.source,
            journal_root=args.journal_root)
        service.start()
        armed = bridge.prepare_and_arm(spec)
        if armed['plan_digest'] != inspection['plan_digest']:
            raise BackupExecutionError('armed plan changed')
        print('ARMED: Press the QNAP physical Copy button ONCE to authorize '
              'this exact single-file backup.', flush=True)
        # Confirmation gate and durable host session both expire after 30s.
        # Never advertise a longer physical authorization window.
        from truepanel.cargo.copy_button import DEFAULT_CONFIRMATION_WINDOW_SECONDS
        deadline = time.monotonic() + DEFAULT_CONFIRMATION_WINDOW_SECONDS - 2.0
        while not bridge.confirmed:
            if time.monotonic() >= deadline:
                raise BackupExecutionError('physical confirmation expired (30-second authorization window); no copy started')
            snapshot = service.snapshot()
            if snapshot.get('last_error'):
                raise BackupExecutionError('GPIO polling error')
            time.sleep(0.1)
        print('CONFIRMED: Performing attested one-file transaction', flush=True)
        result = execute_supervised_single_file(
            plan=plan, inspection=inspection,
            host_bridge=bridge,
            writable_session=SupervisedWriteWindow(
                mount=args.mount, uuid=cart.uuid, by_id=args.by_id),
            registry=args.registry, mount=args.mount,
            by_id=args.by_id, manifest=args.manifest)
        print(json.dumps(result, indent=2), flush=True)
        return 0
    finally:
        try:
            if bridge is not None:
                bridge.disarm()
        finally:
            try:
                if service is not None:
                    service.stop()
            finally:
                owner.release()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'LOADMASTER_ABORTED: {type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
