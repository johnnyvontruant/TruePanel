import copy
import json
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import yaml

from truepanel.web.server import MissionControlServer


class FakeSnapshotService:
    def __init__(self, config):
        self.config = copy.deepcopy(config)


def base_config():
    return {
        "flightdeck": {
            "night_mode": {
                "enabled": True,
                "idle_after": 1800,
                "rotation_interval": 60,
                "suppress_info": True,
                "dashboard_pages": ["home", "storage", "capacity"],
                "backlight_off": True,
                "wake_on_button": True,
                "allow_warning_alerts": True,
                "allow_critical_alerts": True,
            }
        }
    }


@contextmanager
def running_server(tmp_path, *, allow_config_writes):
    config = base_config()
    config_path = tmp_path / "truepanel.yaml"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )
    snapshot = FakeSnapshotService(config)
    server = MissionControlServer(
        ("127.0.0.1", 0),
        snapshot_service=snapshot,
        allow_config_writes=allow_config_writes,
        config_path=config_path,
    )
    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", config_path, snapshot
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def post_json(address, payload):
    request = Request(
        address,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def test_save_is_locked_by_default(tmp_path):
    with running_server(
        tmp_path,
        allow_config_writes=False,
    ) as (base_url, config_path, snapshot):
        before = config_path.read_text(encoding="utf-8")
        status, payload = post_json(
            base_url + "/api/v1/config/night-mode/save",
            {
                "night_mode": {"idle_after": 3600},
                "dry_run": True,
            },
        )
        assert status == 403
        assert payload["error"] == "configuration_writes_disabled"
        assert config_path.read_text(encoding="utf-8") == before
        assert snapshot.config["flightdeck"]["night_mode"]["idle_after"] == 1800


def test_enabled_dry_run_never_writes(tmp_path):
    with running_server(
        tmp_path,
        allow_config_writes=True,
    ) as (base_url, config_path, snapshot):
        before = config_path.read_text(encoding="utf-8")
        status, payload = post_json(
            base_url + "/api/v1/config/night-mode/save",
            {
                "night_mode": {
                    "idle_after": 3600,
                    "rotation_interval": 90,
                },
                "dry_run": True,
            },
        )
        assert status == 200
        assert payload["changed"] is True
        assert payload["persisted"] is False
        assert payload["dry_run"] is True
        assert payload["backup_path"] is None
        assert payload["restart_required"] is False
        assert payload["restart_performed"] is False
        assert config_path.read_text(encoding="utf-8") == before
        assert snapshot.config["flightdeck"]["night_mode"]["idle_after"] == 1800


def test_enabled_save_is_atomic_and_backed_up(tmp_path):
    with running_server(
        tmp_path,
        allow_config_writes=True,
    ) as (base_url, config_path, snapshot):
        before = config_path.read_text(encoding="utf-8")
        status, payload = post_json(
            base_url + "/api/v1/config/night-mode/save",
            {
                "night_mode": {
                    "idle_after": 3600,
                    "rotation_interval": 90,
                },
                "dry_run": False,
            },
        )
        assert status == 200
        assert payload["changed"] is True
        assert payload["persisted"] is True
        assert payload["dry_run"] is False
        assert payload["restart_required"] is True
        assert payload["restart_performed"] is False
        assert payload["writes_enabled"] is True
        backup_path = Path(payload["backup_path"])
        assert backup_path.exists()
        assert backup_path.read_text(encoding="utf-8") == before
        saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        night_mode = saved["flightdeck"]["night_mode"]
        assert night_mode["idle_after"] == 3600
        assert night_mode["rotation_interval"] == 90
        assert snapshot.config["flightdeck"]["night_mode"]["idle_after"] == 3600


def test_unsafe_policy_is_rejected_without_writing(tmp_path):
    with running_server(
        tmp_path,
        allow_config_writes=True,
    ) as (base_url, config_path, snapshot):
        before = config_path.read_text(encoding="utf-8")
        status, payload = post_json(
            base_url + "/api/v1/config/night-mode/save",
            {
                "night_mode": {
                    "allow_critical_alerts": False,
                },
                "dry_run": False,
            },
        )
        assert status == 422
        assert payload["error"] == "configuration_rejected"
        assert config_path.read_text(encoding="utf-8") == before
        assert snapshot.config["flightdeck"]["night_mode"]["allow_critical_alerts"] is True
