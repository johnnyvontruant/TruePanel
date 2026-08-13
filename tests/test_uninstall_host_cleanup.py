import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNINSTALL = ROOT / "uninstall.sh"


def source():
    return UNINSTALL.read_text(encoding="utf-8")


def test_uninstall_shell_syntax_is_valid():
    subprocess.run(
        ["bash", "-n", str(UNINSTALL)],
        check=True,
        cwd=ROOT,
    )


def test_uninstall_stops_every_truepanel_service_before_runtime_cleanup():
    text = source()

    host_stop = text.index(
        'stop_service "$HOST_AGENT_SERVICE_NAME"'
    )
    lcd_stop = text.index(
        'stop_service "$SERVICE_NAME"'
    )
    mission_stop = text.index(
        'stop_service "$MISSION_SERVICE_NAME"'
    )
    runtime_cleanup = text.index(
        'echo "Removing runtime state..."'
    )

    assert host_stop < runtime_cleanup
    assert lcd_stop < runtime_cleanup
    assert mission_stop < runtime_cleanup


def test_uninstall_refuses_cleanup_if_a_service_remains_active():
    text = source()

    assert 'systemctl is-active "$service"' in text
    assert (
        'Refusing to uninstall while %s is still active.'
        in text
    )
    assert "exit 1" in text


def test_uninstall_requires_host_ownership_release_before_runtime_cleanup():
    text = source()

    verify = text.index(
        "assert_host_ownership_released"
    )
    call = text.index(
        "assert_host_ownership_released",
        verify + len("assert_host_ownership_released"),
    )
    cleanup = text.index(
        'echo "Removing runtime state..."'
    )

    assert call < cleanup
    assert "fcntl.LOCK_EX | fcntl.LOCK_NB" in text
    assert (
        "Host hardware ownership is still held; "
        "refusing runtime cleanup."
        in text
    )


def test_uninstall_verifies_fan_automatic_before_destructive_cleanup():
    text = source()

    ownership = text.index(
        "assert_host_ownership_released",
        text.index("== TruePanel Uninstaller =="),
    )
    verify = text.index(
        "verify_fan_safety",
        ownership,
    )
    disable = text.index(
        'echo "Disabling installed services..."'
    )
    cleanup = text.index(
        'echo "Removing runtime state..."'
    )

    assert ownership < verify < disable < cleanup
    assert 'CONFIG_FILE="$INSTALL_DIR/truepanel.yaml"' in text
    assert '"$BIN_FILE" host fan-safety' in text
    assert '--config "$CONFIG_FILE"' in text


def test_uninstall_refuses_fan_verification_without_config_or_cli():
    text = source()

    assert '[[ ! -f "$CONFIG_FILE" ]]' in text
    assert '[[ ! -x "$BIN_FILE" ]]' in text
    assert (
        "Refusing uninstall because fan restoration cannot be verified."
        in text
    )


def test_uninstall_preserves_install_for_diagnosis_when_fan_safety_fails():
    text = source()

    verify_start = text.index(
        "verify_fan_safety()"
    )
    verify_end = text.index(
        "\n}\n",
        verify_start,
    )
    block = text[verify_start:verify_end]

    assert "Motherboard Automatic fan control was not confirmed." in block
    assert (
        "Refusing destructive uninstall cleanup; "
        "installation remains in place."
        in block
    )
    assert "exit 1" in block
    assert 'rm -rf "$INSTALL_DIR"' not in block


def test_uninstall_removes_all_installed_service_scaffolding():
    text = source()

    for path_var in (
        'SERVICE_FILE="/etc/systemd/system/truepanel.service"',
        'MISSION_SERVICE_FILE="/etc/systemd/system/'
        'truepanel-mission-control.service"',
        'HOST_AGENT_SERVICE_FILE="/etc/systemd/system/'
        'truepanel-host-agent.service"',
        'MISSION_ENV_FILE="/etc/default/truepanel-mission-control"',
    ):
        assert path_var in text

    assert (
        'rm -f "$SERVICE_FILE" "$MISSION_SERVICE_FILE" '
        '"$HOST_AGENT_SERVICE_FILE"'
        in text
    )
    assert 'rm -f "$MISSION_ENV_FILE"' in text


def test_uninstall_removes_known_ephemeral_runtime_artifacts():
    text = source()

    for path in (
        "/run/truepanel/standalone-host-agent.enabled",
        "/run/truepanel/host-owner.lock",
        "/run/truepanel/fan-control.sock",
        "/run/truepanel/fan-control-status.json",
        "/run/truepanel/lcd-command.sock",
        "/run/truepanel/lcd-reader-status.json",
        "/run/truepanel/lcd-display-status.json",
    ):
        assert path in text

    assert 'rmdir "$RUNTIME_DIR" 2>/dev/null || true' in text


def test_uninstall_never_starts_or_arms_standalone_host_agent():
    text = source()

    for forbidden in (
        "systemctl start truepanel-host-agent",
        "systemctl restart truepanel-host-agent",
        "systemctl enable truepanel-host-agent",
        "ARM_THERMAL_CONTROL",
        "ENGAGE_AFTERBURNERS",
    ):
        assert forbidden not in text
