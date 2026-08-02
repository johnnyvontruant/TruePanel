import copy
import json
import threading
from contextlib import contextmanager
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from truepanel.hardware.fan_command import (
    AFTERBURNERS_CONFIRMATION,
    THERMAL_ARM_CONFIRMATION,
    SUPERVISED_THERMAL_CONFIRMATION,
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

    def fan_control_history_payload(
        self,
        limit=20,
    ):
        return {
            "schema_version": 1,
            "read_only": True,
            "count": 1,
            "events": [
                {
                    "timestamp": 100.0,
                    "source": "manual",
                    "effective_profile": (
                        "afterburners"
                    ),
                }
            ][-limit:],
        }

    def thermal_commissioning_history_payload(
        self,
        limit=20,
    ):
        return {
            "schema_version": 1,
            "read_only": True,
            "count": 1,
            "events": [
                {
                    "timestamp": 100.0,
                    "lifecycle_action": (
                        "supervised_started"
                    ),
                    "commissioning_state": (
                        "supervised_live"
                    ),
                }
            ][-limit:],
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

    def request_thermal_control(
        self,
        action,
        *,
        confirmation=None,
    ):
        self.calls.append(
            {
                "action": action,
                "confirmation": confirmation,
            }
        )

        if self.error is not None:
            raise self.error

        return copy.deepcopy(
            self.response
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


def test_normal_profiles_are_forwarded_to_socket():
    client = FakeFanCommandClient()

    with running_server(
        client
    ) as base_url:
        for profile in (
            "quiet",
            "balanced",
            "cooling_boost",
        ):
            status, payload = post_json(
                base_url
                + "/api/v1/fans/profile",
                {
                    "profile": profile,
                },
            )

            assert status == 200
            assert payload["ok"] is True

    assert client.calls == [
        {
            "profile": "quiet",
            "confirmation": None,
        },
        {
            "profile": "balanced",
            "confirmation": None,
        },
        {
            "profile": "cooling_boost",
            "confirmation": None,
        },
    ]


def test_unknown_profile_is_rejected_before_socket():
    client = FakeFanCommandClient()

    with running_server(
        client
    ) as base_url:
        status, payload = post_json(
            base_url
            + "/api/v1/fans/profile",
            {
                "profile": "warp_nine",
            },
        )

    assert status == 422
    assert payload["error"] == (
        "unknown_profile"
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


def test_fan_history_endpoint_is_read_only():
    client = FakeFanCommandClient()

    with running_server(client) as base_url:
        with urlopen(
            base_url
            + "/api/v1/fans/history?limit=1",
            timeout=5,
        ) as response:
            status = response.status
            payload = json.load(
                response
            )

    assert status == 200
    assert payload["read_only"] is True
    assert payload["count"] == 1
    assert (
        payload["events"][0][
            "effective_profile"
        ]
        == "afterburners"
    )



def test_commissioning_history_endpoint_is_read_only():
    client = FakeFanCommandClient()

    with running_server(client) as base_url:
        with urlopen(
            base_url
            + (
                "/api/v1/fans/"
                "commissioning-history?limit=1"
            ),
            timeout=5,
        ) as response:
            status = response.status
            payload = json.load(
                response
            )

    assert status == 200
    assert payload["read_only"] is True
    assert payload["count"] == 1
    assert (
        payload["events"][0][
            "lifecycle_action"
        ]
        == "supervised_started"
    )


def test_thermal_arm_route_requires_confirmation():
    client = FakeFanCommandClient()

    with running_server(
        client
    ) as base_url:
        status, payload = post_json(
            base_url
            + "/api/v1/fans/thermal-arm",
            {
                "action": "arm",
            },
        )

    assert status == 409
    assert payload["error"] == (
        "confirmation_required"
    )
    assert client.calls == []


def test_thermal_arm_route_forwards_confirmation():
    client = FakeFanCommandClient(
        response={
            "ok": True,
            "status": "armed",
            "operator_armed": True,
            "dry_run": True,
        }
    )

    with running_server(
        client
    ) as base_url:
        status, payload = post_json(
            base_url
            + "/api/v1/fans/thermal-arm",
            {
                "action": "arm",
                "confirmation": (
                    THERMAL_ARM_CONFIRMATION
                ),
            },
        )

    assert status == 200
    assert payload["operator_armed"] is True
    assert client.calls == [
        {
            "action": "arm",
            "confirmation": (
                THERMAL_ARM_CONFIRMATION
            ),
        }
    ]


def test_thermal_disarm_route_needs_no_confirmation():
    client = FakeFanCommandClient(
        response={
            "ok": True,
            "status": "disarmed",
            "operator_armed": False,
            "dry_run": True,
        }
    )

    with running_server(
        client
    ) as base_url:
        status, payload = post_json(
            base_url
            + "/api/v1/fans/thermal-arm",
            {
                "action": "disarm",
            },
        )

    assert status == 200
    assert payload["operator_armed"] is False
    assert client.calls == [
        {
            "action": "disarm",
            "confirmation": None,
        }
    ]



def test_supervised_live_route_requires_stronger_confirmation():
    client = FakeFanCommandClient()

    with running_server(
        client
    ) as base_url:
        status, payload = post_json(
            base_url
            + "/api/v1/fans/thermal-arm",
            {
                "action": "supervised_live",
                "confirmation": (
                    THERMAL_ARM_CONFIRMATION
                ),
            },
        )

    assert status == 409
    assert payload["error"] == (
        "confirmation_required"
    )
    assert payload[
        "confirmation_required"
    ] == SUPERVISED_THERMAL_CONFIRMATION
    assert client.calls == []


def test_supervised_live_route_forwards_confirmation():
    client = FakeFanCommandClient(
        response={
            "ok": True,
            "status": "supervised_live",
            "supervised_session_active": True,
        }
    )

    with running_server(
        client
    ) as base_url:
        status, payload = post_json(
            base_url
            + "/api/v1/fans/thermal-arm",
            {
                "action": "supervised_live",
                "confirmation": (
                    SUPERVISED_THERMAL_CONFIRMATION
                ),
            },
        )

    assert status == 200
    assert payload[
        "supervised_session_active"
    ] is True
    assert client.calls == [
        {
            "action": "supervised_live",
            "confirmation": (
                SUPERVISED_THERMAL_CONFIRMATION
            ),
        }
    ]
