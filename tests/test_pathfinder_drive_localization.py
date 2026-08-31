from __future__ import annotations

import http.client
import json
import threading

from truepanel.guidance.sessions import RecoverySessionStore
from truepanel.web import pathfinder_server


class _SnapshotService:
    def status(self):
        return {
            "timestamp": 1,
            "operator_guidance": [],
            "storage": {
                "temperatures": [
                    {"device": "sda", "temperature_c": 34},
                    {"device": "sdc", "temperature_c": 45},
                ]
            },
            "fans": {"channels": [], "control": {}},
            "network": [],
        }


class _BayMirror:
    def snapshot(self):
        return {
            "schema_version": 1,
            "read_only_hardware": True,
            "privacy_safe": True,
            "available": True,
            "count": 2,
            "bays": [],
        }

    def device_bay_map(self):
        return {"sda": 1, "sdc": 3}


def _request(server, path):
    host, port = server.server_address
    connection = http.client.HTTPConnection(host, port, timeout=3)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def test_pathfinder_localizes_drive_before_aegis_observes_status(tmp_path):
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
        assert payload["storage"]["temperatures"] == [
            {"device": "sda", "temperature_c": 34, "bay": 1},
            {"device": "sdc", "temperature_c": 45, "bay": 3},
        ]
        assert payload["reliability"]["topology"] == {
            "hottest_drive_temperature_c": 45,
            "hottest_drive_bay": 3,
            "hottest_drive_localized": True,
            "drives_with_known_bay": 2,
            "drives_observed": 2,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
