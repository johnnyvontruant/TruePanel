from dataclasses import FrozenInstanceError

import pytest

from truepanel.host.hooks import (
    HostAgentApplicationHooks,
    HostAgentSafetyServices,
)


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
    assert services.fan_event_recorder is None
    assert services.thermal_control_handler_factory is None
    assert services.fan_reconciliation_factory is None
    assert services.thermal_lifecycle_factory is None


def test_application_hooks_default_none():
    hooks = HostAgentApplicationHooks()

    assert hooks.lcd_button_handler is None


def test_safety_and_application_contracts_are_separate():
    safety_fields = {
        field.name
        for field in (
            HostAgentSafetyServices
            .__dataclass_fields__
            .values()
        )
    }

    application_fields = {
        field.name
        for field in (
            HostAgentApplicationHooks
            .__dataclass_fields__
            .values()
        )
    }

    assert "lcd_button_handler" not in safety_fields

    assert application_fields == {
        "lcd_button_handler"
    }


def test_contracts_are_frozen():
    services = HostAgentSafetyServices(
        fan_telemetry_provider=telemetry
    )

    hooks = HostAgentApplicationHooks()

    with pytest.raises(FrozenInstanceError):
        services.fan_status_publisher = lambda: None

    with pytest.raises(FrozenInstanceError):
        hooks.lcd_button_handler = lambda mask, source: True
