import copy
import json
import threading
from contextlib import contextmanager
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from truepanel.hardware.fan_command import (
    AFTERBURNERS_CONFIRMATION,
    FanCommandError,
)
from truepanel.web.server import (
    MissionControlServer,
)


class FakeSnapshotService:
    def __init__(self):
        self.config = copy.deepcopy(
            {
                "hardware": {
                    "fan_control": {
                        "enabled": True,
                    }
                }
            }
        )

    def status(self):
        return {
            "fans": {
                "control": {
                    "enabled": True,
                    "connected": True,
                }
            }
        }

    def capabilities(self):
        return {}


class FakeFanCommandClient:
    def __init__(
        self,
        *,
        error=None,
        response=None,
    ):
        self.calls = []
        self.error = error
        self.response = (
            response
            or {
                "ok": True,
                "status": "applied",
                "requested_profile": (
                    "automatic"
                ),
                "effective_profile": (
                    "automatic"
                ),
            }
        )

    def request(
        self,
        profile,
        *,
        confirmation=None,
    ):
        self.calls.append(
            {
                "profile": profile,
                "confirmation": confirmation,
            }
        )

        if self.error is not None:
            raise self.error

        return copy.deepcopy(
            self.response
        )


@contextmanager
def running_server(client):
    server = MissionControlServer(
        ("127.0.0.1", 0),
        snapshot_service=(
            FakeSnapshotService()
        ),
        fan_command_client=client,
    )

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()

    try:
        host, port = server.server_address
        yield (
            f"http://{host}:{port}"
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(
            timeout=5
        )


def post_json(
    address,
    payload,
):
    request = Request(
        address,
        data=json.dumps(
            payload
        ).encode(
            "utf-8"
        ),
        headers={
            "Content-Type": (
                "application/json"
            ),
        },
        method="POST",
    )

    try:
        with urlopen(
            request,
            timeout=10,
        ) as response:
            return (
                response.status,
                json.load(response),
            )
    except HTTPError as error:
        return (
            error.code,
            json.load(error),
        )


def test_automatic_route_calls_socket_client():
    client = FakeFanCommandClient()

    with running_server(
        client
    ) as base_url:
        status, payload = post_json(
            base_url
            + "/api/v1/fans/profile",
            {
                "profile": "automatic",
            },
        )

    assert status == 200
    assert payload["ok"] is True
    assert client.calls == [
        {
            "profile": "automatic",
            "confirmation": None,
        }
    ]


def test_afterburners_requires_confirmation():
    client = FakeFanCommandClient()

    with running_server(
        client
    ) as base_url:
        status, payload = post_json(
            base_url
            + "/api/v1/fans/profile",
            {
                "profile": (
                    "afterburners"
                ),
            },
        )

    assert status == 409
    assert payload["error"] == (
        "confirmation_required"
    )
    assert client.calls == []


def test_afterburners_confirmation_is_forwarded():
    client = FakeFanCommandClient(
        response={
            "ok": True,
            "status": "applied",
            "requested_profile": (
                "afterburners"
            ),
            "effective_profile": (
                "afterburners"
            ),
            "pwm": 255,
        }
    )

    with running_server(
        client
    ) as base_url:
        status, payload = post_json(
            base_url
            + "/api/v1/fans/profile",
            {
                "profile": (
                    "afterburners"
                ),
                "confirmation": (
                    AFTERBURNERS_CONFIRMATION
                ),
            },
        )

    assert status == 200
    assert payload[
        "effective_profile"
    ] == "afterburners"
    assert client.calls == [
        {
            "profile": "afterburners",
            "confirmation": (
                AFTERBURNERS_CONFIRMATION
            ),
        }
    ]


def test_locked_profile_is_rejected_before_socket():
    client = FakeFanCommandClient()

    with running_server(
        client
    ) as base_url:
        status, payload = post_json(
            base_url
            + "/api/v1/fans/profile",
            {
                "profile": "quiet",
            },
        )

    assert status == 422
    assert payload["error"] == (
        "profile_locked"
    )
    assert client.calls == []


def test_unknown_fields_are_rejected():
    client = FakeFanCommandClient()

    with running_server(
        client
    ) as base_url:
        status, payload = post_json(
            base_url
            + "/api/v1/fans/profile",
            {
                "profile": "automatic",
                "surprise": True,
            },
        )

    assert status == 400
    assert payload["error"] == (
        "invalid_request"
    )
    assert client.calls == []


def test_socket_failure_returns_503():
    client = FakeFanCommandClient(
        error=FanCommandError(
            "socket unavailable"
        )
    )

    with running_server(
        client
    ) as base_url:
        status, payload = post_json(
            base_url
            + "/api/v1/fans/profile",
            {
                "profile": "automatic",
            },
        )

    assert status == 503
    assert payload["error"] == (
        "fan_command_unavailable"
    )


def test_runtime_rejection_status_is_preserved():
    client = FakeFanCommandClient(
        response={
            "ok": False,
            "status": "disabled",
            "message": (
                "Fan control is disabled."
            ),
        }
    )

    with running_server(
        client
    ) as base_url:
        status, payload = post_json(
            base_url
            + "/api/v1/fans/profile",
            {
                "profile": "automatic",
            },
        )

    assert status == 403
    assert payload["status"] == (
        "disabled"
    )
