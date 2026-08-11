from truepanel.host.telemetry import (
    HostFanTelemetryProvider,
)


def test_snapshot_normalizes_safety_telemetry():
    provider = HostFanTelemetryProvider(
        temperature_provider=lambda: (
            41,
            "48",
            52.5,
            None,
        ),
        fan_status_provider=lambda: {
            "fan1_rpm": 1500,
        },
        clock=lambda: 100.0,
    )

    assert provider.snapshot() == {
        "fan_status": {
            "fan1_rpm": 1500,
        },
        "temperatures_c": (
            41.0,
            48.0,
            52.5,
        ),
        "telemetry_fresh": True,
    }


def test_snapshot_without_temperatures_fails_closed():
    provider = HostFanTelemetryProvider(
        temperature_provider=lambda: (),
        fan_status_provider=dict,
        clock=lambda: 100.0,
    )

    assert provider.snapshot() == {
        "fan_status": {},
        "temperatures_c": (),
        "telemetry_fresh": False,
    }


def test_snapshot_temperature_failure_fails_closed():
    def fail():
        raise RuntimeError(
            "temperature collection failed"
        )

    provider = HostFanTelemetryProvider(
        temperature_provider=fail,
        fan_status_provider=dict,
        clock=lambda: 100.0,
    )

    snapshot = provider.snapshot()

    assert snapshot[
        "temperatures_c"
    ] == ()

    assert (
        snapshot[
            "telemetry_fresh"
        ]
        is False
    )


def test_previous_success_expires_after_freshness_window():
    clock = [100.0]
    temperatures = [(42.0,)]

    provider = HostFanTelemetryProvider(
        temperature_provider=lambda: (
            temperatures[0]
        ),
        fan_status_provider=dict,
        clock=lambda: clock[0],
        freshness_seconds=10.0,
    )

    assert (
        provider.snapshot()[
            "telemetry_fresh"
        ]
        is True
    )

    temperatures[0] = ()
    clock[0] = 111.0

    assert (
        provider.snapshot()[
            "telemetry_fresh"
        ]
        is False
    )


def test_recent_success_remains_fresh_during_short_gap():
    clock = [100.0]
    temperatures = [(42.0,)]

    provider = HostFanTelemetryProvider(
        temperature_provider=lambda: (
            temperatures[0]
        ),
        fan_status_provider=dict,
        clock=lambda: clock[0],
        freshness_seconds=10.0,
    )

    assert (
        provider.snapshot()[
            "telemetry_fresh"
        ]
        is True
    )

    temperatures[0] = ()
    clock[0] = 105.0

    snapshot = provider.snapshot()

    assert snapshot[
        "temperatures_c"
    ] == ()

    assert (
        snapshot[
            "telemetry_fresh"
        ]
        is True
    )


def test_provider_is_callable():
    provider = HostFanTelemetryProvider(
        temperature_provider=lambda: (
            40.0,
        ),
        fan_status_provider=lambda: {
            "ok": True,
        },
        clock=lambda: 100.0,
    )

    assert provider() == provider.snapshot()
