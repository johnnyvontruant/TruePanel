from truepanel.hardware.fan_control import (
    FanProfile,
)
from truepanel.hardware.fan_runtime import (
    FanControlRuntime,
    build_fan_control_runtime,
)


class FakeStatus:
    active_profile = FanProfile.BALANCED
    requested_profile = FanProfile.BALANCED
    remaining_seconds = 42.0
    last_reason = "Balanced profile active."


class FakeService:
    def __init__(self):
        self.shutdown_calls = 0

    def status(self):
        return FakeStatus()

    def shutdown(self):
        self.shutdown_calls += 1


def enabled_config():
    return {
        "hardware": {
            "fan_control": {
                "enabled": True,
                "command_timeout": 120,
                "controlled_channels": [
                    1,
                    2,
                ],
            }
        }
    }


def test_disabled_runtime_constructs_nothing():
    calls = []

    runtime = build_fan_control_runtime(
        {
            "hardware": {
                "fan_control": {
                    "enabled": False,
                }
            }
        },
        controller_factory=lambda: (
            calls.append(
                "controller"
            )
        ),
        interlock_factory=lambda **kwargs: (
            calls.append(
                "interlock"
            )
        ),
        executor_factory=lambda *args, **kwargs: (
            calls.append(
                "executor"
            )
        ),
        service_factory=lambda *args, **kwargs: (
            calls.append(
                "service"
            )
        ),
    )

    assert calls == []
    assert runtime.enabled is False
    assert runtime.connected is False
    assert runtime.status_payload() == {
        "enabled": False,
        "connected": False,
        "active_profile": "automatic",
        "requested_profile": "automatic",
        "remaining_seconds": None,
        "last_reason": (
            "Fan control is disabled."
        ),
    }


def test_enabled_missing_controller_fails_safe():
    runtime = build_fan_control_runtime(
        enabled_config(),
        controller_factory=lambda: None,
    )

    payload = runtime.status_payload()

    assert runtime.enabled is True
    assert runtime.connected is False
    assert payload["active_profile"] == (
        "automatic"
    )
    assert payload["last_reason"] == (
        "Fintek fan controller is unavailable."
    )


def test_enabled_runtime_constructs_full_chain():
    created = {}

    class Interlock:
        pass

    class Executor:
        def __init__(
            self,
            base,
            controlled_channels,
        ):
            created["base"] = base
            created["channels"] = (
                controlled_channels
            )
            self.close_calls = 0

        def close(self):
            self.close_calls += 1

    class Service(FakeService):
        def __init__(
            self,
            interlock,
            executor,
            command_timeout,
        ):
            super().__init__()
            created["interlock"] = (
                interlock
            )
            created["executor"] = (
                executor
            )
            created["timeout"] = (
                command_timeout
            )

    runtime = build_fan_control_runtime(
        enabled_config(),
        controller_factory=lambda: (
            "/fake/hwmon"
        ),
        interlock_factory=lambda **kwargs: (
            Interlock()
        ),
        executor_factory=Executor,
        service_factory=Service,
    )

    assert runtime.connected is True
    assert created["base"] == (
        "/fake/hwmon"
    )
    assert created["channels"] == (
        1,
        2,
    )
    assert created["timeout"] == 120.0

    payload = runtime.status_payload()

    assert payload["connected"] is True
    assert payload["active_profile"] == (
        "balanced"
    )
    assert payload["remaining_seconds"] == (
        42.0
    )


def test_service_construction_failure_closes_executor():
    created = {}

    class Executor:
        def __init__(
            self,
            base,
            controlled_channels,
        ):
            del base
            del controlled_channels
            self.close_calls = 0
            created["executor"] = self

        def close(self):
            self.close_calls += 1

    def fail_service(
        interlock,
        executor,
        command_timeout,
    ):
        del interlock
        del executor
        del command_timeout
        raise RuntimeError(
            "simulated failure"
        )

    runtime = build_fan_control_runtime(
        enabled_config(),
        controller_factory=lambda: (
            "/fake/hwmon"
        ),
        interlock_factory=lambda **kwargs: (
            object()
        ),
        executor_factory=Executor,
        service_factory=fail_service,
    )

    assert runtime.connected is False
    assert (
        created["executor"].close_calls
        == 1
    )
    assert (
        "simulated failure"
        in runtime.status_payload()[
            "last_reason"
        ]
    )


def test_runtime_shutdown_closes_service_once():
    service = FakeService()

    runtime = FanControlRuntime(
        enabled=True,
        service=service,
    )

    runtime.shutdown()
    runtime.shutdown()

    assert service.shutdown_calls == 1
    assert runtime.connected is False


def test_invalid_channels_fall_back_to_verified_pair():
    created = {}

    def executor_factory(
        base,
        controlled_channels,
    ):
        del base
        created["channels"] = (
            controlled_channels
        )

        class Executor:
            def close(self):
                pass

        return Executor()

    runtime = build_fan_control_runtime(
        {
            "hardware": {
                "fan_control": {
                    "enabled": True,
                    "controlled_channels": [
                        3,
                        "bogus",
                    ],
                }
            }
        },
        controller_factory=lambda: (
            "/fake/hwmon"
        ),
        interlock_factory=lambda **kwargs: (
            object()
        ),
        executor_factory=executor_factory,
        service_factory=lambda *args, **kwargs: (
            FakeService()
        ),
    )

    assert runtime.connected is True
    assert created["channels"] == (
        1,
        2,
    )
