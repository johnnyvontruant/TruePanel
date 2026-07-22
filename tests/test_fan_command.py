from dataclasses import dataclass

from truepanel.hardware.fan_command import (
    AFTERBURNERS_CONFIRMATION,
    FanCommandClient,
    FanCommandProcessor,
    FanCommandServer,
)
from truepanel.hardware.fan_control import (
    FanControlDecision,
    FanProfile,
)


@dataclass
class FakeServiceStatus:
    active_profile: FanProfile
    requested_profile: FanProfile
    remaining_seconds: float | None
    last_reason: str


class FakeService:
    def __init__(self):
        self.requests = []
        self.active = (
            FanProfile.AUTOMATIC
        )

    def request_profile(
        self,
        profile,
        *,
        fan_status,
        temperatures_c,
        telemetry_fresh,
    ):
        self.requests.append(
            {
                "profile": profile,
                "fan_status": fan_status,
                "temperatures_c": (
                    temperatures_c
                ),
                "telemetry_fresh": (
                    telemetry_fresh
                ),
            }
        )

        requested = FanProfile(
            profile
        )
        self.active = requested

        return FanControlDecision(
            accepted=True,
            requested_profile=requested,
            effective_profile=requested,
            pwm=(
                None
                if requested
                is FanProfile.AUTOMATIC
                else 255
            ),
            reason="Applied by fake service.",
            force_automatic=(
                requested
                is FanProfile.AUTOMATIC
            ),
        )

    def status(self):
        return FakeServiceStatus(
            active_profile=self.active,
            requested_profile=self.active,
            remaining_seconds=None,
            last_reason=(
                "Applied by fake service."
            ),
        )


class FakeRuntime:
    def __init__(
        self,
        *,
        enabled=True,
        connected=True,
    ):
        self.enabled = enabled
        self.service = (
            FakeService()
            if connected
            else None
        )

    @property
    def connected(self):
        return (
            self.enabled
            and self.service is not None
        )

    def status_payload(self):
        if not self.connected:
            return {
                "enabled": self.enabled,
                "connected": False,
                "active_profile": (
                    "automatic"
                ),
                "requested_profile": (
                    "automatic"
                ),
                "remaining_seconds": None,
                "last_reason": (
                    "Disconnected."
                ),
            }

        status = self.service.status()

        return {
            "enabled": True,
            "connected": True,
            "active_profile": (
                status.active_profile.value
            ),
            "requested_profile": (
                status.requested_profile.value
            ),
            "remaining_seconds": (
                status.remaining_seconds
            ),
            "last_reason": (
                status.last_reason
            ),
        }


def telemetry():
    return {
        "fan_status": {
            "fan_channels": [
                {
                    "number": 1,
                    "rpm": 1500,
                    "alarm": False,
                },
                {
                    "number": 2,
                    "rpm": 1450,
                    "alarm": False,
                },
            ]
        },
        "temperatures_c": (
            50,
            41,
            47,
        ),
        "telemetry_fresh": True,
    }


def test_automatic_is_accepted():
    runtime = FakeRuntime()
    processor = FanCommandProcessor(
        runtime,
        telemetry_provider=telemetry,
    )

    response = processor.process(
        {
            "profile": "automatic",
        }
    )

    assert response["ok"] is True
    assert (
        response["effective_profile"]
        == "automatic"
    )
    assert (
        runtime.service.requests[0][
            "profile"
        ]
        == "automatic"
    )


def test_afterburners_requires_confirmation():
    runtime = FakeRuntime()
    processor = FanCommandProcessor(
        runtime,
        telemetry_provider=telemetry,
    )

    response = processor.process(
        {
            "profile": "afterburners",
        }
    )

    assert response["ok"] is False
    assert (
        response["status"]
        == "confirmation_required"
    )
    assert runtime.service.requests == []


def test_afterburners_with_confirmation_is_accepted():
    runtime = FakeRuntime()
    processor = FanCommandProcessor(
        runtime,
        telemetry_provider=telemetry,
    )

    response = processor.process(
        {
            "profile": "afterburners",
            "confirmation": (
                AFTERBURNERS_CONFIRMATION
            ),
        }
    )

    assert response["ok"] is True
    assert response["pwm"] == 255
    assert (
        response["effective_profile"]
        == "afterburners"
    )


def test_lower_profiles_remain_locked():
    runtime = FakeRuntime()
    processor = FanCommandProcessor(
        runtime,
        telemetry_provider=telemetry,
    )

    for profile in (
        "quiet",
        "balanced",
        "cooling_boost",
    ):
        response = processor.process(
            {
                "profile": profile,
            }
        )

        assert response["ok"] is False
        assert (
            response["status"]
            == "profile_locked"
        )

    assert runtime.service.requests == []


def test_disabled_runtime_rejects_request():
    processor = FanCommandProcessor(
        FakeRuntime(
            enabled=False
        ),
        telemetry_provider=telemetry,
    )

    response = processor.process(
        {
            "profile": "automatic",
        }
    )

    assert response["status"] == (
        "disabled"
    )


def test_disconnected_runtime_rejects_request():
    processor = FanCommandProcessor(
        FakeRuntime(
            connected=False
        ),
        telemetry_provider=telemetry,
    )

    response = processor.process(
        {
            "profile": "automatic",
        }
    )

    assert response["status"] == (
        "disconnected"
    )


def test_status_is_published_after_command():
    calls = []
    processor = FanCommandProcessor(
        FakeRuntime(),
        telemetry_provider=telemetry,
        status_publisher=lambda: (
            calls.append(
                "published"
            )
        ),
    )

    response = processor.process(
        {
            "profile": "automatic",
        }
    )

    assert response["ok"] is True
    assert calls == [
        "published"
    ]


def test_unix_socket_round_trip(
    tmp_path,
):
    socket_path = (
        tmp_path
        / "fan-control.sock"
    )

    runtime = FakeRuntime()
    processor = FanCommandProcessor(
        runtime,
        telemetry_provider=telemetry,
    )
    server = FanCommandServer(
        processor,
        path=socket_path,
    )

    server.start()

    try:
        client = FanCommandClient(
            socket_path
        )

        response = client.request(
            "afterburners",
            confirmation=(
                AFTERBURNERS_CONFIRMATION
            ),
        )

        assert response["ok"] is True
        assert (
            response["effective_profile"]
            == "afterburners"
        )
        assert socket_path.exists()
    finally:
        server.stop()

    assert not socket_path.exists()


def test_socket_rejects_invalid_json(
    tmp_path,
):
    import json
    import socket

    socket_path = (
        tmp_path
        / "fan-control.sock"
    )

    server = FanCommandServer(
        FanCommandProcessor(
            FakeRuntime(),
            telemetry_provider=telemetry,
        ),
        path=socket_path,
    )
    server.start()

    try:
        client = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
        )
        client.connect(
            str(socket_path)
        )
        client.sendall(
            b"not-json\n"
        )
        client.shutdown(
            socket.SHUT_WR
        )

        response = json.loads(
            client.recv(
                4096
            ).decode(
                "utf-8"
            )
        )

        assert response["ok"] is False
        assert (
            response["status"]
            == "invalid_json"
        )
    finally:
        client.close()
        server.stop()
