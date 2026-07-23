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
    control_authority = "manual"
    safety_hold = False
    recovery_pending = False
    recovery_healthy_cycles = 0
    recovery_required_cycles = 3


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
                "afterburners_timeout": 90,
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
        "control_authority": "automatic",
        "safety_hold": False,
        "recovery_pending": False,
        "recovery_healthy_cycles": 0,
        "recovery_required_cycles": 3,
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
            afterburners_timeout,
            safety_recovery_cycles,
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
            created["afterburners_timeout"] = (
                afterburners_timeout
            )
            created["safety_recovery_cycles"] = (
                safety_recovery_cycles
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
    assert (
        created["afterburners_timeout"]
        == 90.0
    )
    assert (
        created["safety_recovery_cycles"]
        == 3
    )

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
        afterburners_timeout,
        safety_recovery_cycles,
    ):
        del interlock
        del executor
        del command_timeout
        del afterburners_timeout
        del safety_recovery_cycles
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


def test_configured_profiles_reach_runtime_factories():
    created = {}

    class Executor:
        def close(self):
            pass

    class Service(FakeService):
        def __init__(
            self,
            interlock,
            executor,
            **kwargs,
        ):
            super().__init__()
            created["service_kwargs"] = kwargs

    def interlock_factory(
        **kwargs,
    ):
        created["interlock_kwargs"] = kwargs
        return object()

    runtime = build_fan_control_runtime(
        {
            "hardware": {
                "fan_control": {
                    "enabled": True,
                    "profiles": {
                        "quiet": {
                            "pwm": 180,
                            "timeout": 45,
                        },
                        "balanced": {
                            "pwm": 205,
                            "timeout": 90,
                        },
                        "cooling_boost": {
                            "pwm": 235,
                            "timeout": 180,
                        },
                        "afterburners": {
                            "pwm": 200,
                            "timeout": 60,
                        },
                    },
                }
            }
        },
        controller_factory=lambda: (
            "/fake/hwmon"
        ),
        interlock_factory=interlock_factory,
        executor_factory=lambda *args, **kwargs: (
            Executor()
        ),
        service_factory=Service,
    )

    assert runtime.connected is True

    profile_pwm = created[
        "interlock_kwargs"
    ]["profile_pwm"]

    assert (
        profile_pwm[
            FanProfile.QUIET
        ]
        == 180
    )
    assert (
        profile_pwm[
            FanProfile.BALANCED
        ]
        == 205
    )
    assert (
        profile_pwm[
            FanProfile.COOLING_BOOST
        ]
        == 235
    )
    assert (
        profile_pwm[
            FanProfile.AFTERBURNERS
        ]
        == 255
    )

    timeouts = created[
        "service_kwargs"
    ]["profile_timeouts"]

    assert (
        timeouts[
            FanProfile.QUIET
        ]
        == 45
    )
    assert (
        timeouts[
            FanProfile.AFTERBURNERS
        ]
        == 60
    )
