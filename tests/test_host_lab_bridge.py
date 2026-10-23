"""Real polling service + existing gate + durable batch journal; FAKE GPIO/USB only."""
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from truepanel.cargo.durable_batch_lab import (
    BatchError, batch_digest, read_receipt, execute_batch,
)
from truepanel.cargo.resumable_rsync_lab import InterruptedTransfer
from truepanel.host.loadmaster_host_lab_bridge import CartridgeIdentity, HostLabBridge


class Reader:
    level = 1
    closed = False

    def read_level(self):
        return self.level

    def close(self):
        self.closed = True


def eventually(predicate, seconds=4):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if predicate():
            return True
        time.sleep(0.005)
    return False


@pytest.fixture
def rig():
    with tempfile.TemporaryDirectory(prefix='lm-host-bridge-') as dirname:
        root = Path(dirname)
        (root/'.loadmaster-lab-only').write_text('LAB_ONLY\n')
        (root/'nas').mkdir()
        (root/'usb').mkdir()
        (root/'nas'/'out.mkv').write_bytes(os.urandom(128 * 1024))
        (root/'usb'/'in.mkv').write_bytes(os.urandom(96 * 1024))
        reader = Reader()
        identity = [CartridgeIdentity('LAB-SPARE', '6ADA-80D5', '2532EA8D421A')]
        events = []
        bridge = HostLabBridge(root=root, reader=reader,
                               identity_reader=lambda: identity[0],
                               event_recorder=events.append,
                               debounce_seconds=.015, poll_seconds=.003,
                               confirmation_window_seconds=.35)
        try:
            yield root, reader, identity, events, bridge
        finally:
            bridge.close()


def entries():
    return [('NAS_TO_USB', 'out.mkv'), ('USB_TO_NAS', 'in.mkv')]


def click(reader):
    time.sleep(.025)
    reader.level = 0
    time.sleep(.08)
    reader.level = 1
    time.sleep(.04)


def run(bridge, reader, batch):
    bridge.arm(batch)
    click(reader)
    assert eventually(lambda: bridge.status()['state'] in ('COMPLETE', 'FAILED'))
    return bridge.status()


def test_real_host_polling_service_dispatches_both_directions(rig):
    root, reader, identity, events, bridge = rig
    b = bridge.prepare(entries())
    assert bridge.status()['state'] == 'PREVIEW'
    assert not (root/'usb'/'out.mkv').exists()
    assert run(bridge, reader, b)['state'] == 'COMPLETE'
    assert (root/'usb'/'out.mkv').read_bytes() == (root/'nas'/'out.mkv').read_bytes()
    assert (root/'nas'/'in.mkv').read_bytes() == (root/'usb'/'in.mkv').read_bytes()
    assert bridge.status()['confirmed_events'] == 1
    assert bridge.status()['verified_files'] == 2
    assert read_receipt(root,b)['state'] == 'COMPLETE'
    assert any(e.get('event') == 'host_lab_complete' for e in events)


def test_unarmed_button_never_copies(rig):
    root, reader, _, _, bridge = rig
    bridge._service.start()
    click(reader)
    assert bridge.status()['state'] == 'IDLE'
    assert not (root/'usb'/'out.mkv').exists()


def test_arm_cannot_be_reused(rig):
    root, reader, _, _, bridge = rig
    b = bridge.prepare(entries())
    assert run(bridge, reader, b)['state'] == 'COMPLETE'
    with pytest.raises(BatchError):
        bridge.arm(b)
    with pytest.raises(BatchError, match='replay'):
        execute_batch(root, b, bridge._service._last_confirmation)


def test_identity_change_prevents_arming(rig):
    root, reader, identity, _, bridge = rig
    b = bridge.prepare(entries())
    identity[0] = CartridgeIdentity('LAB-SPARE', 'WRONG-UUID', '2532EA8D421A')
    with pytest.raises(BatchError, match='identity'):
        bridge.arm(b)
    assert not (root/'usb'/'out.mkv').exists()


def test_identity_change_after_arming_prevents_transfer(rig):
    root, reader, identity, _, bridge = rig
    b = bridge.prepare(entries())
    bridge.arm(b)
    identity[0] = CartridgeIdentity('LAB-SPARE', 'WRONG-UUID', '2532EA8D421A')
    click(reader)
    assert eventually(lambda: bridge.status()['state'] == 'FAILED')
    assert 'identity' in bridge.status()['error']
    assert not (root/'usb'/'out.mkv').exists()


def test_changed_source_after_preview_is_rejected(rig):
    root, reader, _, _, bridge = rig
    b = bridge.prepare(entries())
    (root/'nas'/'out.mkv').write_bytes(b'changed')
    assert run(bridge, reader, b)['state'] == 'FAILED'
    assert not (root/'usb'/'out.mkv').exists()
    assert read_receipt(root,b)['state'] == 'INTERRUPTED'


def test_conflicting_existing_destination_preserved(rig):
    root, reader, _, _, bridge = rig
    b = bridge.prepare(entries())
    (root/'usb'/'out.mkv').write_bytes(b'KEEP ME')
    assert run(bridge, reader, b)['state'] == 'FAILED'
    assert (root/'usb'/'out.mkv').read_bytes() == b'KEEP ME'


def test_duplicate_approval_while_armed_is_refused(rig):
    root, reader, _, _, bridge = rig
    b = bridge.prepare(entries())
    bridge.arm(b)
    with pytest.raises(BatchError, match='idle'):
        bridge.arm(b)
    with pytest.raises(BatchError, match='busy'):
        bridge.prepare(entries())
    click(reader)
    assert eventually(lambda: bridge.status()['state'] == 'COMPLETE')


def test_failure_and_reapproval_reconciles_published_file(rig):
    from truepanel.cargo import durable_batch_lab
    root, reader, identity, events, bridge = rig
    b = bridge.prepare(entries())
    actual = durable_batch_lab.transfer
    count = [0]
    def fail_second(*args, **kwargs):
        count[0] += 1
        if count[0] == 2:
            raise InterruptedTransfer('synthetic loss after completed file')
        return actual(*args, **kwargs)
    with patch.object(durable_batch_lab, 'transfer', side_effect=fail_second):
        assert run(bridge, reader, b)['state'] == 'FAILED'
    assert read_receipt(root,b)['verified'][0]['state'] == 'NEW_VERIFIED_COPY'
    file_data = (root/'usb'/'out.mkv').read_bytes()
    retry = bridge.prepare_retry(b)
    assert batch_digest(retry) != batch_digest(b)
    time.sleep(.85)  # Hardware gate enforces 750ms physical rearm.
    assert run(bridge, reader, retry)['state'] == 'COMPLETE'
    assert (root/'usb'/'out.mkv').read_bytes() == file_data
    assert read_receipt(root,retry)['verified'][0]['state'] == 'PUBLISHED_ALREADY_VERIFIED'
    assert (root/'nas'/'in.mkv').read_bytes() == (root/'usb'/'in.mkv').read_bytes()


def test_identity_change_between_files_interrupts_batch(rig):
    from truepanel.cargo import durable_batch_lab
    root, reader, identity, _, bridge = rig
    b = bridge.prepare(entries())
    actual = durable_batch_lab.transfer
    def swap_after_first(*args, **kwargs):
        result = actual(*args, **kwargs)
        identity[0] = CartridgeIdentity('LAB-SPARE', 'WRONG-UUID', '2532EA8D421A')
        return result
    with patch.object(durable_batch_lab, 'transfer', side_effect=swap_after_first):
        assert run(bridge, reader, b)['state'] == 'FAILED'
    assert (root/'usb'/'out.mkv').exists()
    assert not (root/'nas'/'in.mkv').exists()
    assert read_receipt(root,b)['state'] == 'INTERRUPTED'


def test_non_lab_root_always_refused(tmp_path):
    root = tmp_path / 'bad'
    root.mkdir()
    with pytest.raises(Exception):
        HostLabBridge(root=root, reader=Reader(),
                      identity_reader=lambda: CartridgeIdentity('x','y','z'))


def test_late_press_after_window_never_copies(rig):
    root, reader, _, _, bridge = rig
    b = bridge.prepare(entries())
    bridge.arm(b)
    time.sleep(.43)
    click(reader)
    assert not (root/'usb'/'out.mkv').exists()
    assert bridge.status()['state'] == 'EXPIRED'


def test_close_disarms_and_closes_reader(rig):
    root, reader, _, _, bridge = rig
    b = bridge.prepare(entries())
    bridge.arm(b)
    bridge.close()
    assert reader.closed
    with pytest.raises(BatchError):
        bridge.prepare(entries())
    assert not (root/'usb'/'out.mkv').exists()


def test_held_copy_button_does_not_arm(rig):
    root, reader, _, _, bridge = rig
    b = bridge.prepare(entries())
    reader.level = 0
    with pytest.raises(BatchError, match='release'):
        bridge.arm(b)
    assert bridge.status()['state'] == 'PREVIEW'
    assert not (root/'usb'/'out.mkv').exists()


def test_window_expires_without_a_press(rig):
    root, reader, _, _, bridge = rig
    b = bridge.prepare(entries())
    bridge.arm(b)
    time.sleep(.4)
    assert bridge.status()['state'] == 'EXPIRED'
    assert not (root/'usb'/'out.mkv').exists()


def test_new_plan_requires_readable_identity(rig):
    root, reader, identity, _, bridge = rig
    identity[0] = None
    with pytest.raises(BatchError, match='identity'):
        bridge.prepare(entries())
    assert bridge.status()['state'] == 'IDLE'


def test_disposable_lab_refuses_mount_point(rig):
    root, reader, identity, events, bridge = rig
    from truepanel.cargo import resumable_rsync_lab as lab
    real_ismount = os.path.ismount
    with patch.object(lab.os.path, 'ismount', side_effect=lambda p: (Path(p) == root/'usb') or real_ismount(p)):
        with pytest.raises(lab.LabError, match='mounted media'):
            bridge.prepare(entries())
    assert not (root/'usb'/'out.mkv').exists()
