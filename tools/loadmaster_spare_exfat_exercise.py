#!/usr/bin/env python3
"""Disposable synthetic exFAT exercise on the IDENTIFIED blank Micron spare.

NO production file reads, physical GPIO, device formatting, removal, or
overwriting. Leaves only a new marked test directory on the spare.
"""
import hashlib
import json
import os
import tempfile
from pathlib import Path

from truepanel.cargo.backup_executor import attest_cartridge_read_only
from truepanel.cargo.backup_transaction import _copy_validated_roots
from truepanel.cargo.physical_backup_actuator import _writable_identity
from truepanel.cargo.supervised_mount import SupervisedWriteWindow

MOUNT = Path('/mnt/loadmaster-spare-ro')
BY_ID = '/dev/disk/by-id/usb-Micron_CT8000X10SSD9_2532EA8D421A-0:0-part2'
UUID = '6ADA-80D5'
DEST_NAME = 'LOADMASTER-LAB-20261022'
SSD_PARENT = Path('/mnt/SSDs/Applications')

def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        while chunk := f.read(1024*1024):
            digest.update(chunk)
    return digest.hexdigest()

def main():
    attestation = attest_cartridge_read_only(
        mount=MOUNT, registered_uuid=UUID, registered_by_id=BY_ID)
    if not attestation.matches_registry or not attestation.read_only:
        raise RuntimeError('spare cartridge read-only identity refused')
    if (MOUNT/DEST_NAME).exists():
        raise RuntimeError('test directory already present: never overwrite')
    # Explicitly isolate all test writes from the real TV N-Z cartridge.
    if os.path.realpath(BY_ID) != '/dev/sda2':
        raise RuntimeError('unexpected by-id resolved path; stop')
    if not SSD_PARENT.is_dir():
        raise RuntimeError('missing SSD test parent')
    names = tuple(f'Synthetic Show {i}/episode-{i}.mkv' for i in (1,2,3))
    output = []
    with tempfile.TemporaryDirectory(prefix='loadmaster-spare-source-',dir=SSD_PARENT) as temp:
        nas = Path(temp)
        for index, name in enumerate(names,1):
            source=nas/name
            source.parent.mkdir()
            source.write_bytes(bytes([index])* (8192+index*101))
        with SupervisedWriteWindow(mount=MOUNT, uuid=UUID, by_id=BY_ID):
            _writable_identity(mount=MOUNT, by_id=BY_ID, uuid=UUID)
            usb = MOUNT/DEST_NAME
            usb.mkdir(mode=0o700)
            for name in names:
                source = nas/name
                expected_size=source.stat().st_size
                result=_copy_validated_roots(
                    source_root=nas,usb_root=usb,
                    relative_path=name,expected_size=expected_size)
                if result['sha256'] != sha(source) or sha(usb/name) != sha(source):
                    raise RuntimeError('synthetic checksum mismatch')
                output.append({'relative_path':name,'bytes':expected_size,
                               'sha256':result['sha256'],'state':'VERIFIED'})
    attest_cartridge_read_only(mount=MOUNT,registered_uuid=UUID,registered_by_id=BY_ID)
    print(json.dumps({'state':'SPARE_EXFAT_WRITE_WINDOW_VERIFIED',
                      'spare_uuid':UUID,'spare_serial':'2532EA8D421A',
                      'test_folder':str(MOUNT/DEST_NAME),
                      'files':output,'postflight_read_only':True,
                      'physical_copy_button_used':False},indent=2))

if __name__=='__main__':
    main()
