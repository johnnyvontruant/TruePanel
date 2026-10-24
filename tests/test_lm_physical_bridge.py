"""Host-owned GPIO75 -> Loadmaster v2 authorization boundary."""
from truepanel.cargo.copy_button import CopyButtonConfirmation
from truepanel.loadmaster.physical_bridge import ConfirmationBridge


def confirmation(**changes):
    fields = dict(
        cartridge_id="Untitled",
        cartridge_uuid="6ADA-80D5",
        device_serial="2532EA8D421A",
        plan_digest="a" * 64,
        confirmed_at_monotonic=123.0,
    )
    fields.update(changes)
    return CopyButtonConfirmation(**fields)


def status(**changes):
    result = {
        "available": True, "age": 0.2, "state": "READY",
        "drive": {"name": "Untitled", "uuid": "6ADA-80D5", "serial": "2532EA8D421A"},
        "plan": {"state": "READY", "needs_confirmation": False,
                 "digest": "a" * 64,
                 "summary": {"to_usb_files": 1, "to_usb_bytes": 400,
                             "to_nas_files": 0, "delete_usb_files": 0,
                             "retire_nas_files": 0, "conflicts": 0}},
    }
    result.update(changes)
    return result


def test_bridge_off_by_default():
    sent = []
    bridge = ConfirmationBridge(status_reader=status, sender=lambda x: sent.append(x))
    assert not bridge.accept(confirmation())
    assert not sent


def test_matching_confirmation_dispatches_once():
    sent = []
    bridge = ConfirmationBridge(
        enabled=True, status_reader=status,
        sender=lambda req: (sent.append(req) or {"ok": True, "status": "started"}),
    )
    assert bridge.accept(confirmation())
    assert sent == [{"action": "start", "source": "lcd", "digest": "a" * 64, "confirm": True}]
    assert not bridge.accept(confirmation())
    assert len(sent) == 1


def test_refuses_changed_cartridge_and_plan():
    for changed in [
        confirmation(cartridge_uuid="OTHER"),
        confirmation(device_serial="OTHER"),
        confirmation(plan_digest="b" * 64),
        confirmation(cartridge_id="OTHER"),
    ]:
        sent = []
        bridge = ConfirmationBridge(
            enabled=True, status_reader=status,
            sender=lambda req: sent.append(req),
        )
        assert not bridge.accept(changed)
        assert not sent


def test_refuses_stale_and_nonready():
    for changes in [
        {"available": False}, {"age": 6}, {"state": "CLEAR"},
        {"plan": {**status()["plan"], "needs_confirmation": True}},
        {"plan": {**status()["plan"], "state": "HOLD"}},
    ]:
        sent = []
        bridge = ConfirmationBridge(
            enabled=True, status_reader=lambda: status(**changes),
            sender=lambda req: sent.append(req),
        )
        assert not bridge.accept(confirmation())
        assert not sent


def test_refuses_ingest_deletions_and_conflicts():
    for key in ("to_nas_files", "delete_usb_files", "retire_nas_files", "conflicts"):
        data = status()
        data["plan"]["summary"][key] = 1
        sent = []
        bridge = ConfirmationBridge(
            enabled=True, status_reader=lambda: data,
            sender=lambda req: sent.append(req),
        )
        assert not bridge.accept(confirmation())
        assert not sent


def test_transport_failure_consumes_event():
    calls = []
    def fail(req):
        calls.append(req)
        raise OSError("socket unavailable")
    bridge = ConfirmationBridge(enabled=True, status_reader=status, sender=fail)
    assert not bridge.accept(confirmation())
    assert not bridge.accept(confirmation())
    assert len(calls) == 1
