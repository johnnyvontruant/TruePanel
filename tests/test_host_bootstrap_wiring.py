from pathlib import Path


def source():
    return Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )


def test_lcd_runtime_uses_host_bootstrap():
    text = source()

    assert (
        "host_bootstrap = "
        "build_host_agent_bootstrap("
        in text
    )

    assert (
        "fan_control_runtime = "
        "host_bootstrap.fan_runtime"
        in text
    )

    assert (
        "host_bootstrap.thermal_authority"
        not in text
    )

    assert (
        "host_bootstrap.fan_control_history"
        not in text
    )

    assert (
        "host_bootstrap."
        "thermal_commissioning_history"
        not in text
    )


def test_lcd_runtime_no_longer_constructs_host_dependencies():
    text = source()

    assert "build_fan_control_runtime(" not in text
    assert "HostThermalAuthority(" not in text

    assert (
        "FanControlHistory("
        not in text
    )

    assert (
        "ThermalCommissioningHistory("
        not in text
    )


def test_thermal_observer_is_host_owned():
    runtime = source()
    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text(encoding="utf-8")
    host_runtime = Path(
        "truepanel/host/runtime.py"
    ).read_text(encoding="utf-8")
    reconciliation = Path(
        "truepanel/host/reconciliation.py"
    ).read_text(encoding="utf-8")

    assert "host_agent_runtime.observe_thermal(" in runtime
    assert ".thermal_observer" not in runtime
    assert "HostThermalObserver" in bootstrap
    assert "def observe_thermal(" in host_runtime
    assert "def observe(" in reconciliation
    assert "self._thermal_observer.observe(" in reconciliation

    for application_owned in (
        "ThermalObserverHistory(",
        "ThermalFanPolicy(",
        "event_from_recommendation(",
        "thermal_observer_last_signature",
        "thermal_observer_previous_profile",
    ):
        assert application_owned not in runtime


def test_host_bootstrap_owns_history_behavior():
    runtime = source()
    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text(encoding="utf-8")
    reconciliation = Path(
        "truepanel/host/reconciliation.py"
    ).read_text(encoding="utf-8")
    lifecycle = Path(
        "truepanel/host/thermal_lifecycle.py"
    ).read_text(encoding="utf-8")

    for legacy in (
        "record_thermal_commissioning_event(",
        "record_fan_control_event(",
        "fan_control_event_source(",
    ):
        assert legacy not in runtime

    assert "event_from_decision(" in bootstrap
    assert "commissioning_event(" in bootstrap
    assert "fan_control_history.append(" in bootstrap
    assert "thermal_commissioning_history.append(" in bootstrap
    assert "fan_event_source=self.fan_event_source" in bootstrap
    assert "source_classifier=self._fan_event_source" in reconciliation
    assert "self._record_commissioning_event" in lifecycle


def test_automatic_restoration_is_host_only():
    runtime = source()
    safety = Path(
        "truepanel/host/safety.py"
    ).read_text(encoding="utf-8")
    reconciliation = Path(
        "truepanel/host/reconciliation.py"
    ).read_text(encoding="utf-8")
    lifecycle = Path(
        "truepanel/host/thermal_lifecycle.py"
    ).read_text(encoding="utf-8")

    assert "def restore_motherboard_fan_control(" not in runtime
    assert "def restore_automatic(" in safety
    assert "restore_automatic=self._safety.restore_automatic" in reconciliation
    assert "restore_automatic=self._safety.restore_automatic" in lifecycle
    assert ".request_profile(" not in runtime


def test_lcd_uses_host_owned_telemetry_normalizer():
    runtime = source()
    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text(encoding="utf-8")
    host_runtime = Path(
        "truepanel/host/runtime.py"
    ).read_text(encoding="utf-8")
    host_provider = Path(
        "truepanel/host/telemetry.py"
    ).read_text(encoding="utf-8")
    hardware_provider = Path(
        "truepanel/hardware/drive_temperatures.py"
    ).read_text(encoding="utf-8")

    assert "DriveTemperatureProvider" not in runtime
    assert "HostFanTelemetryProvider" not in runtime
    assert "def fan_command_telemetry(" not in runtime
    assert "DriveTemperatureProvider" in bootstrap
    assert "HostFanTelemetryProvider" in bootstrap
    assert "telemetry=telemetry" in bootstrap
    assert "def fan_telemetry(" in host_runtime
    assert "self._safety.telemetry()" in host_runtime
    assert "class HostFanTelemetryProvider" in host_provider
    assert "class DriveTemperatureProvider" in hardware_provider


def test_lcd_uses_host_owned_status_publisher():
    runtime = source()
    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text(encoding="utf-8")
    host_runtime = Path(
        "truepanel/host/runtime.py"
    ).read_text(encoding="utf-8")

    assert "FanControlStatusBridge" not in runtime
    assert "publish_host_fan_status" not in runtime
    assert "FanControlStatusBridge" in bootstrap
    assert "publish_host_fan_status" in bootstrap

    publisher_start = runtime.index(
        "def publish_fan_control_status("
    )
    publisher_end = runtime.index(
        "\ndef ",
        publisher_start + 1,
    )
    publisher = runtime[publisher_start:publisher_end]

    assert "host_agent_runtime.publish_fan_status(" in publisher
    assert "def publish_fan_status(" in host_runtime
    assert "fan_control_runtime.status_payload()" not in publisher
    assert "fan_control_status_bridge.publish(" not in publisher


def test_lcd_delegates_host_safety_service_assembly():
    runtime = source()

    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "HostAgentSafetyServices" not in runtime
    assert "host_bootstrap.safety_services(" in runtime
    assert "HostAgentSafetyServices" in bootstrap
    assert "def safety_services(" in bootstrap
    assert "fan_telemetry_provider=(" in bootstrap
    assert "fan_status_publisher=(" in bootstrap
    assert "fan_event_recorder=(" in bootstrap
    assert "set_thermal_operator_arm_state" not in runtime
    assert "thermal_control_handler_factory=(" in bootstrap

def test_lcd_delegates_thermal_action_binding_to_host():
    runtime = source()
    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text(encoding="utf-8")
    factory = Path(
        "truepanel/host/factory.py"
    ).read_text(encoding="utf-8")

    assert "set_thermal_operator_arm_state" not in runtime
    assert "host_bootstrap.safety_services()" in runtime
    assert "build_thermal_control_handler" in bootstrap
    assert "thermal_control_handler_factory" in factory
    assert "bind_thermal_control_handler(" in factory
    assert "safety.restore_automatic" in factory

def test_lcd_delegates_reconciliation_construction_to_host():
    runtime = source()
    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text(encoding="utf-8")
    factory = Path(
        "truepanel/host/factory.py"
    ).read_text(encoding="utf-8")
    host_runtime = Path(
        "truepanel/host/runtime.py"
    ).read_text(encoding="utf-8")

    assert "HostFanReconciliationCoordinator" not in runtime
    assert "fan_reconciliation_coordinator" not in runtime
    assert "host_agent_runtime.reconcile_fans()" in runtime
    assert "build_fan_reconciliation" in bootstrap
    assert "fan_reconciliation_factory" in factory
    assert "fan_reconciliation=fan_reconciliation" in factory
    assert "def reconcile_fans(" in host_runtime

def test_lcd_delegates_thermal_lifecycle_to_host_runtime():
    runtime = source()
    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text(encoding="utf-8")
    factory = Path(
        "truepanel/host/factory.py"
    ).read_text(encoding="utf-8")
    host_runtime = Path(
        "truepanel/host/runtime.py"
    ).read_text(encoding="utf-8")
    lifecycle = Path(
        "truepanel/host/thermal_lifecycle.py"
    ).read_text(encoding="utf-8")

    assert "host_bootstrap.thermal_authority" not in runtime
    assert "thermal_authority.end_supervised_session(" not in runtime
    assert "thermal_authority.end_automatic_lease(" not in runtime
    assert "host_agent_runtime.end_supervised_thermal_session(" in runtime
    assert "host_agent_runtime.end_bounded_automatic_lease(" in runtime
    assert "build_thermal_lifecycle" in bootstrap
    assert "thermal_lifecycle_factory" in factory
    assert "thermal_lifecycle=thermal_lifecycle" in factory
    assert "def end_supervised_thermal_session(" in host_runtime
    assert "def end_bounded_automatic_lease(" in host_runtime
    assert "HostThermalLifecycleCoordinator" in lifecycle

def test_lcd_has_no_legacy_thermal_bootstrap_state():
    runtime = source()
    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text(encoding="utf-8")

    for legacy in (
        "thermal_policy_config",
        "thermal_command_cooldown_seconds",
        "_current_thermal_safety_fingerprint",
        "_commissioned_thermal_safety_fingerprint",
        "thermal_safety_fingerprint,",
    ):
        assert legacy not in runtime

    assert "thermal_safety_fingerprint" in bootstrap
    assert "command_cooldown_seconds" in bootstrap
    assert "commissioned_fingerprint" in bootstrap
