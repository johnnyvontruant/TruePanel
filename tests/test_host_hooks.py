from dataclasses import FrozenInstanceError

import pytest

from truepanel.host.hooks import HostAgentSafetyServices


def telemetry():
    return {
        "fan_status": {},
        "temperatures_c": (),
        "telemetry_fresh": True,
    }


def test_safety_services_require_telemetry():
    services = HostAgentSafetyServices(
        fan_telemetry_provider=telemetry
    )

    assert (
        services.fan_telemetry_provider
        is telemetry
    )


def test_optional_safety_services_default_none():
    services = HostAgentSafetyServices(
        fan_telemetry_provider=telemetry
    )

    assert services.fan_status_publisher is None
    assert services.fan_status_reader is None
    assert services.fan_event_recorder is None
    assert services.thermal_control_handler_factory is None
    assert services.fan_reconciliation_factory is None
    assert services.thermal_lifecycle_factory is None


def test_safety_contract_contains_no_application_fields():
    safety_fields = {
        field.name
        for field in (
            HostAgentSafetyServices
            .__dataclass_fields__
            .values()
        )
    }

    assert "lcd_button_handler" not in safety_fields
    assert "application_hooks" not in safety_fields


def test_safety_contract_is_frozen():
    services = HostAgentSafetyServices(
        fan_telemetry_provider=telemetry
    )

    with pytest.raises(FrozenInstanceError):
        services.fan_status_publisher = lambda: None
