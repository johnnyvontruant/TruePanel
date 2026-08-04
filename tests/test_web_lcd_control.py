import copy
import json
import threading
from contextlib import contextmanager
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from truepanel.hardware.lcd_command import (
    LCDCommandError,
)
from truepanel.web.server import (
    MissionControlServer,
)


class FakeSnapshotService:
    def __init__(self):
        self.config = {}

    def status(self):
        return {
            "lcd": {
                "available": True,
                "stale": False,
                "display": {
                    "line1": "TruePanel       ",
                    "line2": "Mission Ready   ",
                },
            }
        }

    def capabilities(self):
        return {}


class FakeFanCommandClient:
    pass


class FakeLCDCommandClient:
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
                "status": "accepted",
                "button": "enter",
                "button_mask": 1,
                "source": "web",
            }
        )

    def request(
        self,
        button,
    ):
        self.calls.append(
            button
        )

        if self.error is not None:
            raise self.error

        response = copy.deepcopy(
            self.response
        )

        response[
            "button"
        ] = button

        return response


@contextmanager
def running_server(client):
    server = MissionControlServer(
        ("127.0.0.1", 0),
        snapshot_service=(
            FakeSnapshotService()
        ),
        fan_command_client=(
            FakeFanCommandClient()
        ),
        lcd_command_client=client,
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


def test_enter_button_is_forwarded():
    client = FakeLCDCommandClient()

    with running_server(
        client
    ) as base_url:
        status, payload = post_json(
            base_url
            + "/api/v1/lcd/button",
            {
                "button": "enter",
            },
        )

    assert status == 200
    assert payload["ok"] is True
    assert payload["button"] == "enter"
    assert client.calls == [
        "enter"
    ]


def test_select_button_is_forwarded():
    client = FakeLCDCommandClient()

    with running_server(
        client
    ) as base_url:
        status, payload = post_json(
            base_url
            + "/api/v1/lcd/button",
            {
                "button": "select",
            },
        )

    assert status == 200
    assert payload["ok"] is True
    assert payload["button"] == "select"
    assert client.calls == [
        "select"
    ]


def test_unknown_button_is_rejected_before_socket():
    client = FakeLCDCommandClient()

    with running_server(
        client
    ) as base_url:
        status, payload = post_json(
            base_url
            + "/api/v1/lcd/button",
            {
                "button": "launch",
            },
        )

    assert status == 422
    assert payload["error"] == (
        "unknown_button"
    )
    assert client.calls == []


def test_unknown_fields_are_rejected_before_socket():
    client = FakeLCDCommandClient()

    with running_server(
        client
    ) as base_url:
        status, payload = post_json(
            base_url
            + "/api/v1/lcd/button",
            {
                "button": "enter",
                "serial": "4d0c",
            },
        )

    assert status == 400
    assert payload["error"] == (
        "invalid_request"
    )
    assert client.calls == []


def test_socket_failure_returns_503():
    client = FakeLCDCommandClient(
        error=LCDCommandError(
            "socket unavailable"
        )
    )

    with running_server(
        client
    ) as base_url:
        status, payload = post_json(
            base_url
            + "/api/v1/lcd/button",
            {
                "button": "enter",
            },
        )

    assert status == 503
    assert payload["error"] == (
        "lcd_command_unavailable"
    )


def test_dispatcher_rejection_returns_503():
    client = FakeLCDCommandClient(
        response={
            "ok": False,
            "status": (
                "dispatcher_unavailable"
            ),
            "message": (
                "LCD dispatcher is unavailable."
            ),
        }
    )

    with running_server(
        client
    ) as base_url:
        status, payload = post_json(
            base_url
            + "/api/v1/lcd/button",
            {
                "button": "select",
            },
        )

    assert status == 503
    assert payload["status"] == (
        "dispatcher_unavailable"
    )
