from __future__ import annotations

import http.client
import json
import threading

from truepanel.activity.web import mission_control_activity
from truepanel.guidance.sessions import RecoverySessionStore
from truepanel.web import pathfinder_server


class _SnapshotService:
    def status(self):
        payload = {
            "timestamp": 1,
            "operator_guidance": [],
            "storage": {
                "temperatures": [],
                "zfs_activity": {
                    "scrub_running": True,
                    "resilver_running": False,
                    "percent": 60,
                },
            },
            "fans": {"channels": [], "control": {}},
            "network": [],
        }
        payload["activity"] = mission_control_activity(payload)
        return payload


class _BayMirror:
    def snapshot(self):
        return {
            "schema_version": 1,
            "read_only_hardware": True,
            "privacy_safe": True,
            "available": True,
            "count": 0,
            "bays": [],
        }

    def device_bay_map(self):
        return {}


def _request(server, path):
    host, port = server.server_address
    connection = http.client.HTTPConnection(host, port, timeout=3)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def test_pathfinder_preserves_observatory_activity_in_status(tmp_path):
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
        status, payload = _request(server, "/api/v1/status")

        assert status == 200
        activity = payload["activity"]
        assert activity["project"] == "OBSERVATORY"
        assert activity["read_only"] is True
        assert activity["production_mutation"] is False
        assert activity["observations"][0]["kind"] == "zfs.scrub"
        assert activity["observations"][0]["progress"] == 0.6
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
