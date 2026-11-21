from __future__ import annotations

import http.client
import threading

import pytest

from truepanel.guidance.sessions import RecoverySessionStore
from truepanel.web import pathfinder_server


class _SnapshotService:
    def status(self):
        return {"timestamp": 1, "operator_guidance": [], "storage": {}, "fans": {}, "network": []}


class _BayMirror:
    def snapshot(self):
        return {"available": True, "count": 0, "bays": []}

    def device_bay_map(self):
        return {}


def _request(server, path):
    host, port = server.server_address
    connection = http.client.HTTPConnection(host, port, timeout=3)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.getheader("Content-Type"), response.read()
    finally:
        connection.close()


@pytest.fixture()
def server(tmp_path):
    instance = pathfinder_server.MissionControlServer(
        ("127.0.0.1", 0),
        snapshot_service=_SnapshotService(),
        recovery_session_store=RecoverySessionStore(None),
        bay_mirror_provider=_BayMirror(),
        lifeline_identify_service=object(),
        config_path=tmp_path / "truepanel.yaml",
    )
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=3)


def test_dashboard_injects_flightdeck_skin_last(server):
    status, content_type, dashboard = _request(server, "/")
    assert status == 200
    assert content_type.startswith("text/html")
    tag = b'<script src="/flightdeck-skin.js" defer></script>'
    assert b"<!-- truepanel-flightdeck-skin -->" in dashboard
    assert dashboard.count(tag) == 1
    # Last injected script, so its stylesheet is appended after the companions'.
    last_script = dashboard.rindex(b"<script src=")
    assert dashboard.index(tag) == last_script


def test_flightdeck_skin_script_is_presentation_only(server):
    status, content_type, script = _request(server, "/flightdeck-skin.js")
    assert status == 200
    assert content_type.startswith("application/javascript")
    source = script.decode("utf-8")
    # Escape hatch and rollback path.
    assert 'requested === "classic"' in source
    assert "truepanel-skin" in source
    # Never talks to the API or the hardware.
    assert "fetch(" not in source
    assert "XMLHttpRequest" not in source
    # LCD keys keep their ids and gain context-aware legends.
    for legend in ('"BACK"', '"NEXT"', '"EJECT"'):
        assert legend in source
    assert "virtualLcdEnter" in source and "virtualLcdSelect" in source


@pytest.mark.parametrize(
    "name",
    [
        "barlow-condensed-latin-600-normal.woff2",
        "barlow-condensed-latin-700-normal.woff2",
        "chivo-latin-400-normal.woff2",
        "chivo-latin-700-normal.woff2",
        "chivo-latin-800-normal.woff2",
        "chivo-mono-latin-400-normal.woff2",
        "chivo-mono-latin-600-normal.woff2",
        "chivo-mono-latin-700-normal.woff2",
    ],
)
def test_vendored_fonts_are_served(server, name):
    status, content_type, body = _request(server, f"/fonts/{name}")
    assert status == 200
    assert content_type == "font/woff2"
    assert body[:4] == b"wOF2"


@pytest.mark.parametrize(
    "path",
    [
        "/fonts/../index.html",
        "/fonts/%2e%2e/index.html",
        "/fonts/OFL-Chivo.txt",
        "/fonts/missing-font.woff2",
        "/fonts/Chivo.WOFF2",
        "/fonts/",
    ],
)
def test_font_route_refuses_anything_else(server, path):
    status, _content_type, _body = _request(server, path)
    assert status == 404
