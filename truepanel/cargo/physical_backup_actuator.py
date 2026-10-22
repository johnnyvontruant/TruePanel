"""Host-only supervised physical transaction for one NAS-to-USB file.

Not wired into TruePanel production. The host must own the GPIO bridge and
provide an already inspected read-only plan before calling this function.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from .backup_coordinator import _action, validate_physical_handoff
from .backup_evidence_commit import commit_verified_backup
from .backup_executor import BackupExecutionError
from .backup_transaction import _copy_validated_roots, _safe_parts
from .cartridges import load_cartridge_registry


def _writable_identity(*, mount: Path, by_id: str, uuid: str) -> None:
    """Reattest exact writable exFAT mount without changing its state."""
    if not str(by_id).startswith('/dev/disk/by-id/'):
        raise BackupExecutionError('device link not trusted')
    try:
        fields = subprocess.check_output(
            ['findmnt', '-n', '-M', str(mount), '-o',
             'SOURCE,TARGET,FSTYPE,OPTIONS', '--raw'],
            text=True, timeout=10).strip().split(None, 3)
        if len(fields) != 4:
            raise BackupExecutionError('writable mount missing')
        device, target, fs, flags = fields
        if (target != str(mount) or fs.lower() != 'exfat' or
                'rw' not in flags.split(',') or 'ro' in flags.split(',')):
            raise BackupExecutionError('writable exFAT mount required')
        observed = subprocess.check_output(
            ['blkid', '-s', 'UUID', '-o', 'value', device],
            text=True, timeout=10).strip()
        if (observed != uuid or
                os.path.realpath(device) != os.path.realpath(by_id) or
                not os.path.realpath(device).startswith('/dev/')):
            raise BackupExecutionError('writable cartridge identity mismatch')
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise BackupExecutionError('writable mount attestation failed') from exc


def execute_supervised_single_file(
    *, plan: dict[str, Any], inspection: dict[str, Any],
    host_bridge: Any, writable_session: Any, registry: Path,
    mount: Path, by_id: str, manifest: Path,
) -> dict[str, Any]:
    """Consume host GPIO approval, verify RW identity, publish, commit.

    Does not arm GPIO, mount, remount, remove, or overwrite files.
    Already-published copies are only reconciled after hash verification.
    """
    a = _action(plan)
    if (not all(p.is_absolute() for p in (registry, mount, manifest))
            or mount.is_symlink() or manifest.is_symlink()
            or inspection.get('state') != 'READ_ONLY_TRANSACTION_ACCEPTED'
            or inspection.get('mount_read_only') is not True
            or inspection.get('destination_absent') is not True):
        raise BackupExecutionError('physical inspection required')
    carts = [c for c in load_cartridge_registry(registry)
             if c.cartridge_id == plan.get('cartridge', {}).get('id')]
    if len(carts) != 1:
        raise BackupExecutionError('cartridge not unique')
    c = carts[0]
    if (c.allow_ingest or c.allow_backup or c.delete_policy != 'never'
            or not c.device_serial or
            not re.fullmatch(r'[A-Za-z0-9]{6,64}', c.device_serial)
            or re.search(r'_' + re.escape(c.device_serial) +
                         r'-[0-9]+:[0-9]+-part[0-9]+$', Path(by_id).name) is None):
        raise BackupExecutionError('cartridge safety or serial mismatch')
    nas = c.source_prefix
    usb = mount / c.usb_relative_path
    if (Path(plan.get('nas_root', '')) != nas or
            Path(plan.get('usb_root', '')) != usb or
            not nas.is_dir() or nas.is_symlink() or
            not usb.is_dir() or usb.is_symlink()):
        raise BackupExecutionError('transfer roots mismatch')
    folder, filename = _safe_parts(a['relative_path'])
    source = nas / folder / filename
    destination = usb / folder / filename
    digest = inspection.get('source_sha256')
    if (inspection.get('source') != str(source) or
            inspection.get('destination') != str(destination) or
            inspection.get('uuid') != c.uuid or
            not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest)):
        raise BackupExecutionError('physical inspection identity mismatch')

    # The host owns the callback. Single-use approval burns its durable
    # journal record before any physical actuator can proceed.
    approval = host_bridge.consume_read_only()
    validated = validate_physical_handoff(
        plan=plan, approval=approval, readiness=inspection)
    if writable_session is None:
        raise BackupExecutionError('host writable mount session required')
    with writable_session:
        _writable_identity(mount=mount, by_id=by_id, uuid=c.uuid)
        if os.path.lexists(destination):
            if destination.is_symlink():
                raise BackupExecutionError('destination collision with symlink')
            state = 'RECOVERED_VERIFIED_COPY'
        else:
            result = _copy_validated_roots(
                source_root=nas, usb_root=usb,
                relative_path=a['relative_path'], expected_size=a['size_bytes'])
            if result['sha256'] != digest:
                raise BackupExecutionError('source changed since inspection')
            state = 'NEW_VERIFIED_COPY'
        evidence = commit_verified_backup(
            source=source, destination=destination, manifest=manifest,
            expected_size=a['size_bytes'], expected_sha256=digest)
    return {'state': 'PHYSICAL_BACKUP_VERIFIED', 'copy_state': state,
            'manifest_state': evidence['state'],
            'plan_digest': validated['plan_digest'],
            'physical_copy': state == 'NEW_VERIFIED_COPY'}


def recover_read_only_evidence(*, registry: Path, backlog: Path, mount: Path,
                               by_id: str, cartridge_id: str,
                               source: Path, manifest: Path) -> dict[str, Any]:
    """Reconcile an interrupted *published* copy, with USB mounted RO.

    No confirmation replay and no write to cartridge. Never treats a
    preexisting destination as verified without hashing both copies.
    """
    import hashlib
    import json
    from .backup_executor import attest_cartridge_read_only
    if (not all(p.is_absolute() for p in
                (registry, backlog, mount, source, manifest))
            or mount.is_symlink() or source.is_symlink()
            or manifest.is_symlink()):
        raise BackupExecutionError('invalid recovery paths')
    carts = [c for c in load_cartridge_registry(registry)
             if c.cartridge_id == cartridge_id]
    if len(carts) != 1:
        raise BackupExecutionError('unknown recovery cartridge')
    c = carts[0]
    if (c.allow_ingest or c.allow_backup or c.delete_policy != 'never'
            or not c.device_serial
            or re.search(r'_' + re.escape(c.device_serial) +
                         r'-[0-9]+:[0-9]+-part[0-9]+$', Path(by_id).name) is None):
        raise BackupExecutionError('recovery cartridge policy mismatch')
    attest_cartridge_read_only(
        mount=mount, registered_uuid=c.uuid, registered_by_id=by_id)
    try:
        relative = source.relative_to(c.source_prefix).as_posix()
        folder, filename = _safe_parts(relative)
    except ValueError as exc:
        raise BackupExecutionError('source outside cartridge prefix') from exc
    usb_root = mount / c.usb_relative_path
    if not usb_root.is_dir() or usb_root.is_symlink():
        raise BackupExecutionError('USB root invalid')
    destination = usb_root / folder / filename
    if not source.is_file() or not destination.is_file():
        raise BackupExecutionError('published recovery copy not present')
    ledger = json.loads(backlog.read_text())
    matches = [i for i in ledger.get('items', [])
               if i.get('current_path') == str(source)]
    if len(matches) != 1:
        raise BackupExecutionError('recovery backlog not unique')
    size = matches[0].get('size_bytes')
    if type(size) is not int or size < 0 or source.stat().st_size != size:
        raise BackupExecutionError('recovery source size mismatch')
    digest = hashlib.sha256()
    with source.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    result = commit_verified_backup(
        source=source, destination=destination,
        manifest=manifest, expected_size=size,
        expected_sha256=digest.hexdigest())
    return {'state': 'READ_ONLY_EVIDENCE_RECONCILED',
            'manifest_state': result['state'], 'cartridge_id': cartridge_id,
            'physical_copy': False}
