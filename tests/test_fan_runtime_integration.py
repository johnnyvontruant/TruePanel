from pathlib import Path


def test_lcd_runtime_builds_fan_control_runtime():
    runtime = Path(
        "lcd-menu.py"
    ).read_text()

    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text()

    assert (
        "build_host_agent_bootstrap("
        in runtime
    )

    assert (
        "fan_control_runtime = "
        "host_bootstrap.fan_runtime"
        in runtime
    )

    assert (
        "build_fan_control_runtime"
        in bootstrap
    )


def test_host_thermal_observer_reads_runtime_status():
    runtime = Path(
        "lcd-menu.py"
    ).read_text()

    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text()

    observer = Path(
        "truepanel/host/thermal_observer.py"
    ).read_text()

    compact_runtime = runtime.replace(
        "\n",
        "",
    ).replace(
        " ",
        "",
    )

    compact_bootstrap = bootstrap.replace(
        "\n",
        "",
    ).replace(
        " ",
        "",
    )

    assert (
        "fan_control_runtime.status_payload()"
        not in compact_runtime
    )

    assert (
        "lambda:fan_runtime.status_payload()"
        in compact_bootstrap
    )

    assert (
        "self._runtime_status_provider()"
        in observer
    )


def test_lcd_runtime_shuts_down_fan_control():
    source = Path(
        "lcd-menu.py"
    ).read_text()

    assert (
        "fan_control_runtime.shutdown()"
        in source
    )


def test_fan_history_uses_post_transition_telemetry():
    safety = Path(
        "truepanel/host/safety.py"
    ).read_text(
        encoding="utf-8"
    )

    start = safety.index(
        "    def reconcile("
    )

    end = safety.index(
        "    def restore_automatic(",
        start,
    )

    reconcile = safety[start:end]

    assert (
        "post_transition_telemetry = ("
        in reconcile
    )

    assert (
        "self.telemetry()"
        in reconcile
    )

    assert (
        "self.record_event("
        in reconcile
    )

    assert (
        "post_transition_telemetry,"
        in reconcile
    )


def test_host_classifies_completed_safety_recovery():
    runtime = Path("lcd-menu.py").read_text()
    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text()
    reconciliation = Path(
        "truepanel/host/reconciliation.py"
    ).read_text()

    assert "def fan_control_event_source(" not in runtime
    assert '"safety recovery confirmed"' in bootstrap
    assert 'return "recovery"' in bootstrap
    assert "fan_event_source=self.fan_event_source" in bootstrap
    assert "source_classifier=self._fan_event_source" in reconciliation


def test_host_preserves_timeout_classification():
    runtime = Path("lcd-menu.py").read_text()
    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text()

    assert "host_bootstrap.fan_event_source(" not in runtime
    assert 'and "expired" in reason_lower' in bootstrap
    assert 'return "timeout"' in bootstrap


def test_lcd_delegates_fan_reconciliation_to_host():
    runtime = Path("lcd-menu.py").read_text()
    host_runtime = Path(
        "truepanel/host/runtime.py"
    ).read_text()

    assert "HostFanReconciliationCoordinator" not in runtime
    assert "fan_reconciliation_coordinator" not in runtime
    assert "host_agent_runtime.reconcile_fans()" in runtime
    assert "def reconcile_fans(" in host_runtime
    assert "host_agent_runtime.safety.reconcile(" not in runtime
    assert "thermal_authority.reconcile(" not in runtime


def test_lcd_uses_bootstrap_owned_host_telemetry():
    runtime = Path("lcd-menu.py").read_text()
    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text()

    assert "DriveTemperatureProvider" not in runtime
    assert "HostFanTelemetryProvider" not in runtime
    assert "get_fan_status" not in runtime
    assert "host_bootstrap\n        .telemetry" not in runtime
    assert "host_agent_runtime.observe_thermal(" in runtime
    assert "DriveTemperatureProvider" in bootstrap
    assert "HostFanTelemetryProvider" in bootstrap


def test_lcd_uses_bootstrap_owned_status_bridge():
    runtime = Path("lcd-menu.py").read_text()
    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text()

    assert "FanControlStatusBridge" not in runtime
    assert "publish_host_fan_status" not in runtime
    assert "host_agent_runtime.publish_fan_status(" in runtime
    assert "host_bootstrap.status_bridge.read(" not in runtime
    assert "host_agent_runtime.read_fan_status(" in runtime
    assert "FanControlStatusBridge" in bootstrap


def test_lcd_wires_fan_control_status_page():
    text = Path("lcd-menu.py").read_text()

    assert "fan_control_page" in text
    assert "def show_fan_control():" in text
    assert (
        "host_agent_runtime.read_fan_status("
        in text
    )
    assert (
        "host_bootstrap.status_bridge.read("
        not in text
    )


def test_fan_control_page_sits_between_rpm_and_pwm():
    text = Path("lcd-menu.py").read_text()

    menu_start = text.index(
        "menu = ["
    )
    menu_end = text.index(
        "]",
        menu_start,
    )
    menu = text[
        menu_start:menu_end
    ]

    assert (
        menu.index("show_fan_rpm")
        < menu.index("show_fan_control")
        < menu.index("show_fan_pwm")
    )
