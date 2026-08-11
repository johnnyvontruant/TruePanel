from dataclasses import FrozenInstanceError

import pytest

from truepanel.host.hooks import (
    HostAgentApplicationHooks,
)


def telemetry():
    return {
        "fan_status": {},
        "temperatures_c": (),
        "telemetry_fresh": True,
    }


def test_hooks_require_telemetry_provider():
    hooks = HostAgentApplicationHooks(
        fan_telemetry_provider=telemetry
    )

    assert (
        hooks.fan_telemetry_provider
        is telemetry
    )


def test_optional_hooks_default_to_none():
    hooks = HostAgentApplicationHooks(
        fan_telemetry_provider=telemetry
    )

    assert hooks.fan_status_publisher is None
    assert hooks.fan_event_recorder is None
    assert hooks.thermal_control_handler is None
    assert hooks.lcd_button_handler is None


def test_hooks_preserve_supplied_callbacks():
    def publish():
        pass

    def record(
        decision,
        telemetry_payload,
    ):
        del decision
        del telemetry_payload

    def thermal(action):
        return {
            "action": action,
        }

    def submit_button(
        button_mask,
        source,
    ):
        del button_mask
        del source
        return True

    hooks = HostAgentApplicationHooks(
        fan_telemetry_provider=telemetry,
        fan_status_publisher=publish,
        fan_event_recorder=record,
        thermal_control_handler=thermal,
        lcd_button_handler=submit_button,
    )

    assert hooks.fan_status_publisher is publish
    assert hooks.fan_event_recorder is record
    assert hooks.thermal_control_handler is thermal
    assert hooks.lcd_button_handler is submit_button


def test_hooks_are_frozen():
    hooks = HostAgentApplicationHooks(
        fan_telemetry_provider=telemetry
    )

    with pytest.raises(FrozenInstanceError):
        hooks.fan_status_publisher = lambda: None
