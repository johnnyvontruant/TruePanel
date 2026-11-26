"""Mission Control honours the installed module list (TruePanel 2.0)."""

from __future__ import annotations

import copy
import http.client
import json
import subprocess
import sys
import threading

import pytest

from truepanel.guidance.sessions import RecoverySessionStore
from truepanel.loadmaster import load_settings
from truepanel.modules import resolve, selection_from_config
from truepanel.modules import web as modules_web
from truepanel.web import pathfinder_server
from truepanel.web.snapshot import SnapshotService

CORE_ONLY = {"modules": {"installed": []}}


class _SnapshotService:
    def __init__(self, payload, config=None):
        self.payload = payload
        self.config = config

    def status(self):
        return copy.deepcopy(self.payload)


class _BayMirror:
    def snapshot(self):
        return {"available": False, "count": 0, "bays": []}


class _Aegis:
    def observe(self, payload):
        return {"project": "AEGIS", "state": "NOMINAL"}


def _payload():
    return {"operator_guidance": [], "health": {}, "storage": {}}


@pytest.fixture
def make_server(tmp_path):
    servers = []

    def make(config=None):
        server = pathfinder_server.MissionControlServer(
            ("127.0.0.1", 0),
            snapshot_service=_SnapshotService(_payload(), config),
            recovery_session_store=RecoverySessionStore(None),
            aegis_reliability=_Aegis(),
            bay_mirror_provider=_BayMirror(),
            lifeline_identify_service=object(),
            config_path=tmp_path / "truepanel.yaml",
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return server

    yield make
    for server in servers:
        server.shutdown()
        server.server_close()


def _request(server, method, path, body=None):
    host, port = server.server_address
    connection = http.client.HTTPConnection(host, port, timeout=3)
    try:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        if data:
            headers["Content-Length"] = str(len(data))
        connection.request(method, path, body=data, headers=headers)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


# ------------------------------------------------------------ legacy installs


def test_legacy_config_keeps_every_feature(make_server):
    server = make_server(config={})
    status, raw = _request(server, "GET", "/api/v1/status")
    payload = json.loads(raw)
    assert status == 200
    assert payload["modules"]["legacy"] is True
    assert "pathfinder_recovery" in payload
    assert payload["reliability"]["project"] == "AEGIS"

    status, html = _request(server, "GET", "/")
    assert b"/recovery-workflow.js" in html
    assert b"/reliability-view.js" in html
    assert modules_web.MODULES_MARKER not in html


def test_legacy_routes_are_not_blocked(make_server):
    server = make_server(config={})
    for path in modules_web.ROUTE_MODULES:
        if path.startswith("/api/v1/loadmaster") or path.endswith(".js"):
            status, raw = _request(server, "GET", path)
            assert b"module_not_installed" not in raw, path


# ------------------------------------------------------------- core only


def test_core_only_status_drops_optional_sections(make_server):
    server = make_server(config=CORE_ONLY)
    status, raw = _request(server, "GET", "/api/v1/status")
    payload = json.loads(raw)
    assert status == 200
    assert payload["modules"]["legacy"] is False
    assert set(payload["modules"]["installed"]) == {
        "flight_deck",
        "mission_control",
        "health",
        "history",
        "flight_recorder",
        "lifecycle",
    }
    assert "hardware_control" not in payload["modules"]["installed"]
    assert "pathfinder_recovery" not in payload
    assert "reliability" not in payload
    # Core guidance still flows.
    assert "operator_checklists" in payload


def test_core_only_dashboard_skips_scripts_and_hides_panels(make_server):
    server = make_server(config=CORE_ONLY)
    status, html = _request(server, "GET", "/")
    assert status == 200
    assert b"/recovery-workflow.js" not in html
    assert b"/reliability-view.js" not in html
    assert modules_web.MODULES_MARKER in html
    for selector in (b"#cardCargoBay", b"#cardLoadmaster", b".vpn-interface"):
        assert selector in html
    # Core companions are still served.
    assert b"/fault-view.js" in html
    assert b"/flightdeck-skin.js" in html


@pytest.mark.parametrize("path", sorted(modules_web.ROUTE_MODULES))
def test_core_only_blocks_module_routes(make_server, path):
    server = make_server(config=CORE_ONLY)
    method = "POST" if path in {
        "/api/v1/loadmaster/command",
        "/api/v1/fans/profile",
        "/api/v1/fans/thermal-arm",
        "/api/v1/lifeline/identify",
        "/api/v1/recovery/transition",
    } else "GET"
    status, raw = _request(server, method, path, body={} if method == "POST" else None)
    payload = json.loads(raw)
    assert status == 404
    assert payload["error"] == "module_not_installed"
    assert payload["module"] == modules_web.ROUTE_MODULES[path]


def test_core_routes_stay_open_when_core_only(make_server):
    server = make_server(config=CORE_ONLY)
    for path in ("/api/v1/status", "/fault-view.js", "/api/v1/flight-logs"):
        status, raw = _request(server, "GET", path)
        assert b"module_not_installed" not in raw, path


def test_installed_module_route_is_served(make_server):
    server = make_server(config={"modules": {"installed": ["guided_recovery"]}})
    status, html = _request(server, "GET", "/")
    assert b"/recovery-workflow.js" in html
    assert b"/reliability-view.js" not in html
    status, _ = _request(server, "GET", "/recovery-workflow.js")
    assert status == 200


# ------------------------------------------------------- snapshot service


def _snapshot_service(config):
    service = SnapshotService.__new__(SnapshotService)
    service.config = config
    service.module_selection = selection_from_config(config)
    service.cargo_provider = None
    service.vpn_status_provider = None
    return service


def test_snapshot_omits_cargo_and_vpn_when_not_installed():
    result = _snapshot_service(CORE_ONLY)._with_cargo_bay({"x": 1})
    assert result == {"x": 1}


def test_snapshot_keeps_cargo_and_vpn_for_legacy():
    service = _snapshot_service({})
    service._cargo_bay_payload = lambda: {"available": False}
    result = service._with_cargo_bay({})
    assert "cargo_bay" in result
    assert "vpn" in result


# ------------------------------------------------------------- loadmaster


def _loadmaster_config(installed):
    config = {
        "loadmaster": {
            "enabled": True,
            "drives": [{"name": "TV A-M", "nas_path": "/mnt/HDDs/Shows/TV A-M"}],
        }
    }
    if installed is not None:
        config["modules"] = {"installed": installed}
    return config


def test_loadmaster_settings_require_the_module():
    assert load_settings(_loadmaster_config([])) is None
    assert load_settings(_loadmaster_config(["loadmaster"])) is not None
    assert load_settings(_loadmaster_config(None)) is not None


# ------------------------------------------------------------- import cost


def test_aegis_is_not_imported_when_reliability_is_not_installed():
    code = (
        "import sys\n"
        "from truepanel.web import pathfinder_server\n"
        "from truepanel.modules import resolve\n"
        "class S:\n"
        "    config = {'modules': {'installed': []}}\n"
        "    def status(self): return {}\n"
        "server = pathfinder_server.MissionControlServer(('127.0.0.1', 0),"
        " snapshot_service=S(), bay_mirror_provider=object(),"
        " lifeline_identify_service=object())\n"
        "server.server_close()\n"
        "assert server.aegis_reliability is None\n"
        "assert server.recovery_session_store is None\n"
        "print('truepanel.aegis' in sys.modules)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


def test_dashboard_tag_is_empty_when_everything_is_installed():
    assert modules_web.dashboard_tag(selection_from_config({})) == b""
    assert modules_web.dashboard_tag(resolve(["cargo_bay"])) != b""


def test_every_mapped_module_exists_and_is_optional():
    from truepanel.modules import MODULES

    for module_id in {*modules_web.ROUTE_MODULES.values(), *modules_web.PANEL_SELECTORS}:
        assert MODULES[module_id].removable, module_id
