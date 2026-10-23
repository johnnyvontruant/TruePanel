from __future__ import annotations

import json
from pathlib import Path

import pytest
from loadmaster_fixtures import make_bay

from truepanel.cargo.backlog import write_backlog_atomic
from truepanel.cargo.copy_button import CopyButtonConfirmation
from truepanel.cargo.dock import BlockDevice, DockedCartridge, DockScan
from truepanel.cargo.executor import ExecutorSettings
from truepanel.cargo.loadmaster import inventory_payload
from truepanel.host.factory import build_loadmaster_controller
from truepanel.host.loadmaster_controller import (
    LoadmasterController,
    LoadmasterControllerSettings,
    settings_from_config,
)


class FakeDock:
    def __init__(self, mount: Path) -> None:
        self.mount = mount
        self.present: list[DockedCartridge] = []
        self.calls: list[str] = []

    def scan(self) -> DockScan:
        return DockScan(docked=tuple(self.present), unknown_usb_filesystems=0)

    def mount_read_only(self, docked):
        self.calls.append("ro")
        return self.mount

    def remount_read_write(self, docked):
        self.calls.append("rw")
        return self.mount

    def release(self, docked, *, lazy=False):
        self.calls.append("release")

    def release_orphan(self, cartridge_id):
        self.calls.append("orphan")


class FakeButton:
    def __init__(self) -> None:
        self.armed = None
        self.disarms: list[str] = []

    def arm(self, preflight):
        if not preflight.ready:
            raise ValueError("not ready")
        self.armed = preflight

    def disarm(self, *, reason="operator"):
        self.armed = None
        self.disarms.append(reason)


class Clock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value


def docked_for(bay, *, verified=True) -> DockedCartridge:
    device = BlockDevice(
        path="/dev/sdh1",
        uuid=bay.cartridge.uuid,
        fstype="exfat",
        label="MOVIES",
        serial="2532EA8D3ED1",
        transport="usb",
        removable=True,
        mountpoints=(),
        size_bytes=1,
    )
    return DockedCartridge(
        bay.cartridge,
        device,
        verified,
        "UUID_ONLY" if verified else "DEVICE_SERIAL_MISMATCH",
    )


def rig(tmp_path, *, commission=True):
    bay = make_bay(tmp_path)
    bay.nas("Heat (1995)/Heat.mkv", b"heat")
    bay.usb("Heat (1995)/Heat.mkv", b"heat")
    baseline = bay.baseline()
    bay.nas("Inception (2010)/Inception.mkv", b"dream")
    bay.usb("Elf (2003)/Elf.mkv", b"buddy")

    state = tmp_path / "state"
    (state / "inventory").mkdir(parents=True)
    registry = state / "cartridges.json"
    registry.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "truepanel.loadmaster_cartridge_registry",
                "cartridges": [
                    {
                        "id": bay.cartridge.cartridge_id,
                        "label": bay.cartridge.label,
                        "uuid": bay.cartridge.uuid,
                        "role": "movies",
                        "source_prefix": str(bay.nas_root),
                        "usb_relative_path": "Movies E-I",
                    }
                ],
            }
        )
    )
    write_backlog_atomic(
        state / "pending-cargo.json", bay.backlog("Inception (2010)/Inception.mkv")
    )
    if commission:
        (state / "inventory" / "movies-e-i.json").write_text(
            json.dumps(
                inventory_payload(
                    cartridge=bay.cartridge,
                    files=baseline,
                    captured_at="2026-10-01T00:00:00+00:00",
                )
            )
        )

    settings = LoadmasterControllerSettings(
        registry_path=registry,
        backlog_path=state / "pending-cargo.json",
        inventory_dir=state / "inventory",
        receipts_dir=state / "receipts",
        manifest_path=state / "backup-manifest.json",
        executor=ExecutorSettings(free_space_margin_bytes=0),
    )
    dock = FakeDock(bay.usb_mount)
    button = FakeButton()
    clock = Clock()
    controller = LoadmasterController(
        settings=settings,
        button=button,
        dock_factory=lambda cartridges: dock,
        clock=clock,
        run_in_thread=False,
    )
    return bay, controller, dock, button, clock


def press(button) -> CopyButtonConfirmation:
    armed = button.armed
    return CopyButtonConfirmation(
        cartridge_id=armed.cartridge_id,
        cartridge_uuid=armed.cartridge_uuid,
        device_serial=armed.device_serial,
        plan_digest=armed.plan_digest,
        confirmed_at_monotonic=0.0,
    )


def test_plug_in_press_copy_complete_then_unplug(tmp_path):
    bay, controller, dock, button, _clock = rig(tmp_path)

    controller.tick()
    assert controller.snapshot()["state"] == "IDLE"

    dock.present = [docked_for(bay)]
    controller.tick()

    status = controller.snapshot()
    assert status["state"] == "READY"
    assert status["armed"] is True
    assert button.armed.backup_files == 1
    assert button.armed.ingest_files == 1

    controller.on_confirmation(press(button))

    status = controller.snapshot()
    assert status["state"] == "COMPLETE"
    assert status["reason"] == "safe to remove"
    assert status["safe_to_remove"] is True
    assert status["last_receipt"]["summary"]["copied_files"] == 2
    assert dock.calls == ["ro", "rw", "release"]
    assert (bay.usb_root / "Inception (2010)/Inception.mkv").exists()
    assert (bay.nas_root / "Elf (2003)/Elf.mkv").exists()

    # Same insertion never re-arms or re-runs.
    controller.tick()
    assert controller.snapshot()["state"] == "COMPLETE"
    assert button.armed is None

    dock.present = []
    controller.tick()
    assert controller.snapshot()["state"] == "IDLE"


def test_uncommissioned_cartridge_holds(tmp_path):
    bay, controller, dock, button, _clock = rig(tmp_path, commission=False)
    dock.present = [docked_for(bay)]

    controller.tick()

    status = controller.snapshot()
    assert status["state"] == "HOLD"
    assert status["reason"].startswith("NOT_COMMISSIONED")
    assert button.armed is None


def test_unverified_identity_holds_without_mounting(tmp_path):
    bay, controller, dock, button, _clock = rig(tmp_path)
    dock.present = [docked_for(bay, verified=False)]

    controller.tick()

    assert controller.snapshot()["state"] == "HOLD"
    assert dock.calls == []
    assert button.armed is None


def test_multiple_cartridges_hold(tmp_path):
    bay, controller, dock, button, _clock = rig(tmp_path)
    dock.present = [docked_for(bay), docked_for(bay)]

    controller.tick()

    assert controller.snapshot()["reason"].startswith("MULTIPLE_CARTRIDGES")


def test_stale_confirmation_is_ignored(tmp_path):
    bay, controller, dock, button, _clock = rig(tmp_path)
    dock.present = [docked_for(bay)]
    controller.tick()
    confirmation = press(button)

    stale = CopyButtonConfirmation(
        cartridge_id=confirmation.cartridge_id,
        cartridge_uuid=confirmation.cartridge_uuid,
        device_serial=confirmation.device_serial,
        plan_digest="not-the-current-plan",
        confirmed_at_monotonic=0.0,
    )
    controller.on_confirmation(stale)

    assert controller.snapshot()["state"] == "READY"
    assert "rw" not in dock.calls


def test_replan_rearms_after_interval(tmp_path):
    bay, controller, dock, button, clock = rig(tmp_path)
    dock.present = [docked_for(bay)]
    controller.tick()
    first = button.armed

    controller.tick()
    assert button.armed is first  # no replan inside the interval

    clock.value += 25
    controller.tick()
    assert button.armed is not first
    assert button.armed.plan_digest == first.plan_digest


def test_settings_require_explicit_enable():
    base = {
        "mission_control": {
            "cargo_bay": {
                "loadmaster": {
                    "enabled": True,
                    "cartridge_registry_path": "/var/lib/x/cartridges.json",
                    "backlog_path": "/var/lib/x/pending.json",
                    "execution": {
                        "enabled": False,
                        "inventory_dir": "/var/lib/x/inventory",
                        "receipts_dir": "/var/lib/x/receipts",
                    },
                }
            }
        }
    }
    assert settings_from_config(base) is None
    assert build_loadmaster_controller(config=base, copy_button_service=None) is None

    base["mission_control"]["cargo_bay"]["loadmaster"]["execution"]["enabled"] = True
    settings = settings_from_config(base)
    assert settings is not None
    assert settings.ingest_enabled is True
    assert settings.executor.verify == "sha256"

    with pytest.raises(ValueError, match="physical_confirmation"):
        build_loadmaster_controller(config=base, copy_button_service=None)


def test_factory_binds_copy_confirmation_to_controller():
    class Service:
        on_confirmation = None

    config = {
        "mission_control": {
            "cargo_bay": {
                "loadmaster": {
                    "enabled": True,
                    "cartridge_registry_path": "/var/lib/x/cartridges.json",
                    "backlog_path": "/var/lib/x/pending.json",
                    "execution": {
                        "enabled": True,
                        "inventory_dir": "/var/lib/x/inventory",
                        "receipts_dir": "/var/lib/x/receipts",
                        "ingest_owner": "568:568",
                    },
                }
            }
        }
    }
    service = Service()
    controller = build_loadmaster_controller(config=config, copy_button_service=service)

    assert service.on_confirmation == controller.on_confirmation
    assert controller.settings.executor.ingest_owner == (568, 568)
