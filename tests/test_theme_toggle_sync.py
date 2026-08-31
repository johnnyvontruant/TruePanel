from __future__ import annotations

import http.client
import threading

from truepanel.guidance.sessions import RecoverySessionStore
from truepanel.web import pathfinder_server


class _SnapshotService:
    def status(self):
        return {
            "timestamp": 1,
            "operator_guidance": [],
            "storage": {},
            "fans": {},
            "network": [],
        }


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


def test_production_dashboard_serves_effective_theme_toggle_sync(tmp_path):
    server = pathfinder_server.MissionControlServer(
        ("127.0.0.1", 0),
        snapshot_service=_SnapshotService(),
        recovery_session_store=RecoverySessionStore(None),
        bay_mirror_provider=_BayMirror(),
        lifeline_identify_service=object(),
        config_path=tmp_path / "truepanel.yaml",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, content_type, dashboard = _request(server, "/")
        assert status == 200
        assert content_type.startswith("text/html")
        assert b"<!-- truepanel-theme-toggle-sync -->" in dashboard
        assert b'<script src="/theme-toggle-sync.js" defer></script>' in dashboard

        status, content_type, script = _request(server, "/theme-toggle-sync.js")
        assert status == 200
        assert content_type.startswith("application/javascript")
        source = script.decode("utf-8")
        assert 'root.dataset.theme' in source
        assert 'prefers-color-scheme: dark' in source
        assert 'darkPreference.addEventListener("change", syncThemeToggle)' in source
        assert 'new MutationObserver(syncThemeToggle)' in source
        assert 'Switch to light mode' in source
        assert 'Switch to dark mode' in source
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
