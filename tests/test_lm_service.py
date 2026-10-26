from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from truepanel.loadmaster import build_service, load_settings
from truepanel.loadmaster.config import LoadmasterConfigError, Settings
from truepanel.loadmaster.dock import Device, Dock, Docked, parse_lsblk
from truepanel.loadmaster.link import (
    CommandServer,
    plan_path_for,
    read_plan,
    read_status,
    send_command,
    validate,
)
from truepanel.loadmaster.servarr import host_path, poll
from truepanel.loadmaster.service import ButtonWatcher, LoadmasterService
from truepanel.loadmaster.state import StateStore

T = 1_700_000_000_000_000_000


def put(root: Path, rel: str, data: bytes, mtime: int = T) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, ns=(mtime, mtime))


class FakeDock:
    """Mount = the drive's folder on disk; records calls."""

    def __init__(self, mount: Path) -> None:
        self.mount = mount
        self.present: list[Docked] = []
        self.calls: list[str] = []

    def scan(self):
        return list(self.present)

    def mount_ro(self, docked):
        self.calls.append("ro")
        return self.mount

    def mount_rw(self, docked):
        self.calls.append("rw")
        return self.mount

    def release(self, docked):
        self.calls.append("release")

    def release_vanished(self, key):
        self.calls.append("vanished")


def device(uuid="AAAA-0001", label="TV A-M"):
    return Device("/dev/sdh1", uuid, "exfat", label, "SER1", True, 1, ())


@pytest.fixture
def svc(tmp_path):
    config = {
        "loadmaster": {
            "enabled": True,
            "state_dir": str(tmp_path / "state"),
            "copy_button": False,
            "drives": [{"name": "TV A-M", "nas_path": str(tmp_path / "nas/TV A-M")}],
        }
    }
    settings = load_settings(config)
    settings = Settings(
        **{
            **settings.__dict__,
            "status_path": tmp_path / "status.json",
            "command_socket": tmp_path / "lm.sock",
        }
    )
    (tmp_path / "nas/TV A-M").mkdir(parents=True)
    (tmp_path / "usb/TV A-M").mkdir(parents=True)
    dock = FakeDock(tmp_path / "usb")
    service = LoadmasterService(settings, dock=dock)
    service.t = tmp_path
    service.fake = dock
    service.nas = tmp_path / "nas/TV A-M"
    service.usb = tmp_path / "usb/TV A-M"
    return service


def plug(svc, uuid="AAAA-0001"):
    svc.fake.present = [Docked(svc.settings.drives[0], device(uuid))]
    svc.tick()
    svc.drain()


def test_plug_press_sync_unplug(svc):
    put(svc.nas, "Show/S01E01.mkv", b"one")
    put(svc.usb, "Show/S01E02.mkv", b"two")

    svc.tick()
    assert svc.state == "IDLE"

    plug(svc)
    status = read_status(svc.settings.status_path)
    assert status["state"] == "READY"
    assert status["plan"]["summary"]["to_usb_files"] == 1
    assert status["plan"]["summary"]["to_nas_files"] == 1
    assert status["plan"]["first_sync"] is True

    svc.press()
    assert svc.state == "COPYING"
    svc.drain()

    assert svc.state == "DONE"
    assert "Safe to remove" in svc.message
    assert svc.fake.calls == ["ro", "ro", "rw", "release"]
    assert (svc.usb / "Show/S01E01.mkv").exists()
    assert (svc.nas / "Show/S01E02.mkv").exists()
    assert read_status(svc.settings.status_path)["safe_to_remove"] is True

    svc.tick()  # same insertion never runs twice
    assert svc.state == "DONE"
    svc.fake.present = []
    svc.tick()
    assert svc.state == "IDLE"

    plug(svc)  # replug: in sync now
    assert svc.state == "CLEAR"


def test_first_sync_with_nothing_to_copy_records_the_baseline(svc):
    # Movies T-Z came up CLEAR on its first sync and stayed "never synced",
    # so a later Radarr upgrade was held as TWO_VERSIONS instead of mirrored.
    put(svc.nas, "Heat (1995)/Heat 720p.mkv", b"old")
    put(svc.usb, "Heat (1995)/Heat 720p.mkv", b"old")
    plug(svc)
    assert svc.state == "CLEAR"
    record = svc.store.load_record("tv-a-m", "TV A-M")
    assert record.known
    assert set(record.files) == {"Heat (1995)/Heat 720p.mkv"}

    svc.fake.present = []
    svc.tick()
    (svc.nas / "Heat (1995)/Heat 720p.mkv").unlink()  # Radarr upgrade
    put(svc.nas, "Heat (1995)/Heat 2160p.mkv", b"new and better")
    plug(svc)
    assert svc.state == "READY"
    ops = sorted((a["op"], a["path"]) for a in svc.plan["actions"])
    assert ops == [
        ("delete_usb", "Heat (1995)/Heat 720p.mkv"),
        ("to_usb", "Heat (1995)/Heat 2160p.mkv"),
    ]


def test_whole_plan_is_published_for_review_and_cleared_on_unplug(svc):
    for i in range(60):
        put(svc.nas, f"Show/S01E{i:02}.mkv", bytes([i]))
    plug(svc)
    status = read_status(svc.settings.status_path)
    assert len(status["plan"]["preview"]) == 40  # the status keeps a preview
    full = read_plan(plan_path_for(svc.settings.status_path))["plan"]
    assert full["digest"] == status["plan"]["digest"]
    assert full["drive"] == "TV A-M" and len(full["actions"]) == 60
    assert "in_sync" not in full

    svc.fake.present = []
    svc.tick()
    assert read_plan(plan_path_for(svc.settings.status_path))["plan"] is None


def test_state_changes_play_one_tone_each(svc):
    heard = []
    svc.sound = heard.append
    put(svc.nas, "Show/S01E01.mkv", b"one")
    plug(svc)
    svc.press()
    svc.drain()
    assert heard == ["CHECKING", "READY", "COPYING", "DONE"]

    def broken(state):
        raise OSError("no speaker")

    svc.sound = broken  # a missing speaker never stops the service
    svc.fake.present = []
    svc.tick()
    assert svc.state == "IDLE"


def test_plan_changed_after_press_is_refused(svc):
    put(svc.nas, "a.mkv", b"a")
    plug(svc)
    svc.press()
    put(svc.nas, "b.mkv", b"b")  # Sonarr import lands between press and run
    svc.drain()

    assert svc.state == "READY"
    assert "changed" in svc.message
    assert not (svc.usb / "a.mkv").exists()
    assert svc.plan["summary"]["to_usb_files"] == 2


def test_remote_start_needs_digest_and_confirmation(svc):
    put(svc.nas, "a.mkv", b"a")
    plug(svc)
    digest = svc.plan["digest"]

    assert (
        svc.handle({"action": "start", "source": "web", "digest": "0" * 64})["status"]
        == "plan_changed"
    )
    assert svc.handle({"action": "start", "source": "web", "digest": digest})["ok"]
    svc.drain()
    assert svc.state == "DONE"


def test_large_removal_needs_truepanel_confirmation(svc):
    svc.settings = Settings(**{**svc.settings.__dict__, "large_delete_files": 2})
    for i in range(5):
        put(svc.nas, f"m{i}.mkv", b"x")
    put(svc.nas, "keep.mkv", b"k")
    plug(svc)
    svc.press()
    svc.drain()
    svc.fake.present = []
    svc.tick()
    for i in range(5):
        (svc.nas / f"m{i}.mkv").unlink()

    plug(svc)
    assert svc.state == "CONFIRM"
    svc.press()
    assert svc.state == "CONFIRM"  # button alone is not enough

    reply = svc.handle(
        {"action": "start", "source": "web", "digest": svc.plan["digest"]}
    )
    assert reply["ok"]
    svc.drain()
    assert svc.state == "DONE"
    assert not (svc.usb / "m0.mkv").exists()


def test_different_physical_drive_needs_adopt(svc):
    put(svc.nas, "a.mkv", b"a")
    plug(svc)
    svc.press()
    svc.drain()
    svc.fake.present = []
    svc.tick()

    plug(svc, uuid="BBBB-0002")
    assert svc.state == "NEW_DRIVE"
    assert svc.handle({"action": "adopt", "source": "web"})["ok"]
    svc.drain()
    assert svc.state == "CLEAR"  # same files, now known under the new ID
    assert svc.plan["first_sync"] is True
    assert svc.record.uuid == "BBBB-0002"


def test_eject_and_rescan(svc):
    put(svc.nas, "a.mkv", b"a")
    plug(svc)
    assert svc.handle({"action": "eject", "source": "lcd"})["ok"]
    assert svc.state == "EJECTED"
    svc.tick()
    assert svc.state == "EJECTED"
    assert svc.handle({"action": "rescan", "source": "web"})["ok"]
    svc.drain()
    assert svc.state == "READY"


def test_two_drives_hold(svc):
    svc.fake.present = [
        Docked(svc.settings.drives[0], device()),
        Docked(svc.settings.drives[0], device("X")),
    ]
    svc.tick()
    assert svc.state == "HOLD"


def test_missing_usb_folder_holds(svc):
    svc.usb.rmdir()
    plug(svc)
    assert svc.state == "HOLD"
    assert "is not on the drive" in svc.message


def test_pending_summary_without_drive(svc):
    put(svc.nas, "a.mkv", b"a")
    plug(svc)
    svc.press()
    svc.drain()
    put(svc.nas, "b.mkv", b"bb")
    svc._refresh_drive_summaries()
    status = read_status(svc.settings.status_path)
    assert status["drives"][0]["pending_files"] == 1
    assert status["next_drive"] == "TV A-M"


def test_stale_status_is_unavailable(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps({"published": time.time() - 999, "status": {"state": "X"}})
    )
    assert read_status(path)["available"] is False
    assert read_status(tmp_path / "none.json")["state"] == "OFF"


# --------------------------------------------------------------- link


def test_validate_requests():
    assert validate({"action": "eject", "source": "web"})[0]
    start = {"action": "start", "source": "web", "digest": "a" * 64, "confirm": True}
    assert validate(start) == (start, None)
    assert validate({"action": "delete", "source": "web"})[1]["status"] == "invalid"
    assert validate({"action": "eject", "source": "gpio"})[1]
    assert validate({"action": "eject", "source": "web", "x": 1})[1]
    assert (
        validate({"action": "start", "source": "web", "digest": "a" * 64})[1]["status"]
        == "confirmation_required"
    )


def test_socket_round_trip():
    folder = Path(tempfile.mkdtemp(dir="/tmp"))
    seen = []
    server = CommandServer(folder / "s.sock", lambda r: seen.append(r) or {"ok": True})
    server.start()
    try:
        assert send_command(folder / "s.sock", {"action": "rescan", "source": "lcd"})[
            "ok"
        ]
    finally:
        server.stop()
    assert seen == [{"action": "rescan", "source": "lcd"}]


# --------------------------------------------------------------- button


def test_button_debounces_and_fires_once_per_press():
    level = {"v": 1}
    presses = []
    watcher = ButtonWatcher(
        lambda: level["v"], lambda: presses.append(1), debounce=0.03, interval=0.005
    )
    watcher.start()
    try:
        level["v"] = 0
        time.sleep(0.01)
        level["v"] = 1  # bounce shorter than debounce
        time.sleep(0.05)
        assert presses == []
        level["v"] = 0
        time.sleep(0.15)
        assert presses == [1]  # held: still one press
        level["v"] = 1
        time.sleep(0.05)
        level["v"] = 0
        time.sleep(0.1)
        assert presses == [1, 1]
    finally:
        watcher.stop()


def test_build_service_without_button_hardware(tmp_path):
    config = {
        "loadmaster": {
            "enabled": True,
            "state_dir": str(tmp_path),
            "drives": [{"name": "TV A-M", "nas_path": "/x/TV A-M"}],
        }
    }

    def no_hardware():
        raise PermissionError("/dev/port")

    service = build_service(config, button_reader_factory=no_hardware)
    assert service.snapshot()["button"].startswith("unavailable")

    assert build_service({"loadmaster": {"enabled": False}}) is None


def test_button_reader_is_closed_on_shutdown(tmp_path):
    class Reader:
        closed = False

        def read_level(self):
            return 1

        def close(self):
            Reader.closed = True

    config = {
        "loadmaster": {
            "enabled": True,
            "state_dir": str(tmp_path),
            "drives": [{"name": "TV A-M", "nas_path": "/x/TV A-M"}],
        }
    }
    service = build_service(config, button_reader_factory=Reader)
    service.settings = Settings(
        **{
            **service.settings.__dict__,
            "status_path": tmp_path / "s.json",
            "command_socket": tmp_path / "s.sock",
        }
    )
    service.dock = FakeDock(tmp_path)
    service.start_service()
    assert service.snapshot()["button"] == "ready"
    service.stop_service()
    assert Reader.closed


# --------------------------------------------------------------- config


def test_config_validation():
    good = {"name": "TV A-M", "nas_path": "/mnt/HDDs/Shows/TV A-M"}
    settings = load_settings({"loadmaster": {"enabled": True, "drives": [good]}})
    assert settings.drives[0].usb_folder == "TV A-M"
    assert settings.drives[0].key == "tv-a-m"
    assert settings.drives[0].protected == ()
    guarded = load_settings(
        {
            "loadmaster": {
                "enabled": True,
                "drives": [{**good, "protected": ["Daria (1997)/"]}],
            }
        }
    )
    assert guarded.drives[0].protected == ("Daria (1997)",)
    for bad in (
        [],
        [{"name": "", "nas_path": "/x"}],
        [{"name": "A", "nas_path": "relative"}],
        [good, dict(good)],
        [good, {"name": "Inner", "nas_path": "/mnt/HDDs/Shows/TV A-M/x"}],
        [{**good, "usb_folder": "../escape"}],
        [{**good, "protected": "Daria (1997)"}],
        [{**good, "protected": ["../Daria"]}],
        [{**good, "protected": [""]}],
    ):
        with pytest.raises(LoadmasterConfigError):
            load_settings({"loadmaster": {"enabled": True, "drives": bad}})


# --------------------------------------------------------------- dock


LSBLK = json.dumps(
    {
        "blockdevices": [
            {
                "path": "/dev/sdh",
                "serial": "S1",
                "tran": "usb",
                "children": [
                    {
                        "path": "/dev/sdh1",
                        "uuid": "U1",
                        "fstype": "exfat",
                        "label": "tv a-m",
                        "size": 5,
                        "mountpoints": [None],
                    }
                ],
            },
            {
                "path": "/dev/sda",
                "serial": "S2",
                "tran": "sata",
                "children": [
                    {
                        "path": "/dev/sda1",
                        "uuid": "U2",
                        "fstype": "exfat",
                        "label": "TV N-Z",
                        "size": 5,
                        "mountpoints": [None],
                    }
                ],
            },
        ]
    }
)


def _dock(tmp_path, mountinfo=""):
    settings = load_settings(
        {
            "loadmaster": {
                "enabled": True,
                "drives": [
                    {"name": "TV A-M", "nas_path": "/n/a"},
                    {"name": "TV N-Z", "nas_path": "/n/b"},
                ],
            }
        }
    )
    calls = []

    def runner(argv):
        calls.append(list(argv))
        return LSBLK if argv[0] == "lsblk" else ""

    return Dock(
        settings.drives, tmp_path / "mnt", runner=runner, mountinfo=lambda: mountinfo
    ), calls


def test_dock_matches_usb_label_only(tmp_path):
    dock, _ = _dock(tmp_path)
    found = dock.scan()
    assert [d.drive.name for d in found] == ["TV A-M"]  # SATA disk ignored
    assert parse_lsblk(LSBLK)[0].serial == "S1"


# util-linux 2.38 on TrueNAS 25.10 prints a flat list even with --tree; only
# the disk carries TRAN/SERIAL. Shape copied from BattleStation.
LSBLK_FLAT = json.dumps(
    {
        "blockdevices": [
            {
                "path": "/dev/sda",
                "pkname": None,
                "serial": "2532EA8D3E2B",
                "tran": "usb",
            },
            {"path": "/dev/sda1", "pkname": "sda", "serial": None, "tran": None},
            {
                "path": "/dev/sda2",
                "pkname": "sda",
                "uuid": "6988-AEDE",
                "fstype": "exfat",
                "label": "TV A-M",
                "serial": None,
                "tran": None,
                "size": 8001546092544,
                "mountpoints": [None],
            },
            {"path": "/dev/sdb", "pkname": None, "serial": "WKD3MW7K", "tran": "sata"},
            {
                "path": "/dev/sdb1",
                "pkname": "sdb",
                "uuid": "5997857175939697463",
                "fstype": "zfs_member",
                "label": "TV N-Z",
                "tran": None,
                "mountpoints": [None],
            },
        ]
    }
)


def test_dock_finds_usb_drive_in_flat_lsblk_output(tmp_path):
    devices = {d.path: d for d in parse_lsblk(LSBLK_FLAT)}
    assert devices["/dev/sda2"].usb is True
    assert devices["/dev/sda2"].serial == "2532EA8D3E2B"
    assert devices["/dev/sdb1"].usb is False

    settings = load_settings(
        {
            "loadmaster": {
                "enabled": True,
                "drives": [
                    {"name": "TV A-M", "nas_path": "/n/a"},
                    {"name": "TV N-Z", "nas_path": "/n/b"},
                ],
            }
        }
    )
    dock = Dock(
        settings.drives,
        tmp_path / "mnt",
        runner=lambda argv: LSBLK_FLAT,
        mountinfo=lambda: "",
    )
    assert [(d.drive.name, d.device.uuid) for d in dock.scan()] == [
        ("TV A-M", "6988-AEDE")
    ]


def test_dock_mounts_read_only_then_read_write(tmp_path):
    dock, calls = _dock(tmp_path)
    docked = dock.scan()[0]
    point = dock.mount_ro(docked)
    assert calls[-1] == [
        "mount",
        "-t",
        "exfat",
        "-o",
        "ro,nosuid,nodev,noexec,noatime",
        "/dev/sdh1",
        str(point),
    ]
    dock.mountinfo = lambda: f"1 2 8:1 / {point} ro,noatime - exfat /dev/sdh1 ro\n"
    dock.mount_rw(docked)
    assert calls[-1][:3] == ["mount", "-o", "remount,rw,nosuid,nodev,noexec,noatime"]
    dock.release(docked)
    assert calls[-2:] == [["sync"], ["umount", str(point)]]


def test_dock_refuses_drive_mounted_elsewhere(tmp_path):
    dock, _ = _dock(tmp_path, "1 2 8:1 / /media/usb rw - exfat /dev/sdh1 rw\n")
    docked = dock.scan()[0]
    assert dock.mount_state(docked) == "ELSEWHERE"
    with pytest.raises(Exception, match="elsewhere"):
        dock.mount_ro(docked)


# --------------------------------------------------------------- servarr


class FakeClient:
    def __init__(self, records):
        self.records = records

    def get(self, endpoint, params=None):
        return {"records": self.records}


def test_servarr_log_maps_imports_to_drives(tmp_path):
    settings = load_settings(
        {
            "loadmaster": {
                "enabled": True,
                "drives": [{"name": "TV A-M", "nas_path": "/mnt/HDDs/Shows/TV A-M"}],
            },
            "mission_control": {
                "cargo_bay": {
                    "sonarr": {
                        "url": "http://x",
                        "config_path": "/c.xml",
                        "media_prefix": "/media/tv",
                        "host_prefix": "/mnt/HDDs/Shows",
                    }
                }
            },
        }
    )
    store = StateStore(tmp_path)
    records = [{"id": 5, "eventType": "downloadFolderImported", "sourceTitle": "old"}]
    poll(settings, store, client_factory=lambda c: FakeClient(records))
    assert store.recent_activity() == []  # first poll only sets the cursor

    records.append(
        {
            "id": 6,
            "eventType": "downloadFolderImported",
            "sourceTitle": "Andor S02E01",
            "data": {"importedPath": "/media/tv/TV A-M/Andor/S02E01.mkv"},
        }
    )
    status = poll(settings, store, client_factory=lambda c: FakeClient(records))
    entry = store.recent_activity()[0]
    assert status["sonarr"].startswith("ok")
    assert entry["drive"] == "TV A-M"
    assert entry["path"] == "/mnt/HDDs/Shows/TV A-M/Andor/S02E01.mkv"
    assert host_path(settings.sonarr, "/elsewhere/x") == Path("/elsewhere/x")


def test_servarr_failure_is_reported_not_raised(tmp_path):
    settings = load_settings(
        {
            "loadmaster": {
                "enabled": True,
                "drives": [{"name": "A", "nas_path": "/a"}],
            },
            "mission_control": {
                "cargo_bay": {
                    "radarr": {
                        "url": "http://x",
                        "config_path": "/c.xml",
                        "host_prefix": "/m",
                    }
                }
            },
        }
    )

    class Down:
        def get(self, *a, **k):
            raise OSError("connection refused")

    status = poll(settings, StateStore(tmp_path), client_factory=lambda c: Down())
    assert status["radarr"].startswith("unreachable")
