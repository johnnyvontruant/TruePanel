import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from truepanel.web.server import MissionControlServer


class FakeSnapshotService:
    def __init__(self):
        self.config = {
            "flightdeck": {
                "night_mode": {
                    "enabled": True,
                    "idle_after": 1800,
                    "rotation_interval": 60,
                    "suppress_info": True,
                    "dashboard_pages": [
                        "home",
                        "storage",
                        "capacity",
                    ],
                    "backlight_off": True,
                    "wake_on_button": True,
                    "allow_warning_alerts": True,
                    "allow_critical_alerts": True,
                }
            }
        }

    def status(self):
        return {"read_only": True}

    def history(self, limit=240):
        return {
            "read_only": True,
            "count": 0,
            "samples": [],
            "limit": limit,
        }

    def capabilities(self):
        return {"safety": {"read_only": True}}


def request_json(address, method="GET", payload=None):
    data = None
    headers = {}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(
        address,
        data=data,
        headers=headers,
        method=method,
    )

    with urlopen(request, timeout=5) as response:
        return response.status, json.load(response)


def running_server():
    server = MissionControlServer(
        ("127.0.0.1", 0),
        snapshot_service=FakeSnapshotService(),
    )

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()

    return server, thread


def test_current_night_mode_policy_is_read_only():
    server, thread = running_server()

    try:
        host, port = server.server_address
        status, payload = request_json(
            f"http://{host}:{port}/api/v1/config/night-mode"
        )

        assert status == 200
        assert payload["read_only"] is True
        assert payload["night_mode"]["idle_after"] == 1800
        assert payload["night_mode"]["dashboard_pages"] == [
            "home",
            "storage",
            "capacity",
        ]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_night_mode_preview_never_persists():
    server, thread = running_server()

    try:
        host, port = server.server_address
        status, payload = request_json(
            f"http://{host}:{port}/api/v1/config/night-mode/preview",
            method="POST",
            payload={
                "night_mode": {
                    "idle_after": 3600,
                    "rotation_interval": 90,
                }
            },
        )

        assert status == 200
        assert payload["read_only"] is True
        assert payload["persisted"] is False
        assert payload["preview"]["changed"] is True
        assert payload["preview"]["proposed"]["idle_after"] == 3600
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_night_mode_preview_rejects_unsafe_policy():
    server, thread = running_server()

    try:
        host, port = server.server_address

        try:
            request_json(
                f"http://{host}:{port}/api/v1/config/night-mode/preview",
                method="POST",
                payload={
                    "allow_critical_alerts": False,
                },
            )
        except HTTPError as error:
            payload = json.loads(
                error.read().decode("utf-8")
            )

            assert error.code == 422
            assert payload["error"] == "configuration_rejected"
            assert "allow_critical_alerts" in payload["message"]
        else:
            raise AssertionError(
                "Unsafe night-mode policy was accepted"
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_unrelated_post_remains_blocked():
    server, thread = running_server()

    try:
        host, port = server.server_address

        try:
            request_json(
                f"http://{host}:{port}/api/v1/status",
                method="POST",
                payload={},
            )
        except HTTPError as error:
            payload = json.loads(
                error.read().decode("utf-8")
            )

            assert error.code == 405
            assert payload["error"] == "read_only"
        else:
            raise AssertionError(
                "Unrelated POST unexpectedly succeeded"
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
