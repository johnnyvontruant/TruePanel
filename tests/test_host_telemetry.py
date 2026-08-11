from truepanel.host.telemetry import (
    HostFanTelemetryProvider,
)


def test_snapshot_normalizes_safety_telemetry():
    provider = HostFanTelemetryProvider(
        state_provider=lambda: {
            "temps": [
                {"temp": 41},
                {"temperature": "48"},
                {"temperature_c": 52.5},
                {"temp": None},
                "invalid",
            ],
            "last_updated": 95.0,
        },
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


def test_snapshot_marks_old_state_stale():
    provider = HostFanTelemetryProvider(
        state_provider=lambda: {
            "temps": [],
            "last_updated": 80.0,
        },
        fan_status_provider=dict,
        clock=lambda: 100.0,
    )

    assert (
        provider.snapshot()[
            "telemetry_fresh"
        ]
        is False
    )


def test_snapshot_marks_missing_timestamp_stale():
    provider = HostFanTelemetryProvider(
        state_provider=lambda: {
            "temps": [],
        },
        fan_status_provider=dict,
        clock=lambda: 100.0,
    )

    assert (
        provider.snapshot()[
            "telemetry_fresh"
        ]
        is False
    )


def test_provider_is_callable():
    provider = HostFanTelemetryProvider(
        state_provider=lambda: {
            "temps": [],
            "last_updated": 100.0,
        },
        fan_status_provider=lambda: {
            "ok": True,
        },
        clock=lambda: 100.0,
    )

    assert provider() == provider.snapshot()
