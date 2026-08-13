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
    assert '"${verifier[@]}" host fan-safety' in text
    assert '--config "$CONFIG_FILE"' in text


def test_uninstall_supports_legacy_fan_safety_without_installed_wrapper():
    text = source()

    assert 'SOURCE_CLI="$SCRIPT_DIR/truepanel.py"' in text
    assert 'VENV_PYTHON="$INSTALL_DIR/.venv/bin/python"' in text
    assert '[[ -x "$BIN_FILE" ]]' in text
    assert (
        '[[ -x "$VENV_PYTHON" && -f "$SOURCE_CLI" ]]'
        in text
    )
    assert 'verifier=("$BIN_FILE")' in text
    assert (
        'verifier=("$VENV_PYTHON" "$SOURCE_CLI")'
        in text
    )
    assert (
        "Installed CLI wrapper unavailable; using current source CLI "
        "with installed runtime."
        in text
    )


def test_uninstall_refuses_fan_verification_without_config_or_any_cli_path():
    text = source()

    assert '[[ ! -f "$CONFIG_FILE" ]]' in text
    assert 'Legacy Python runtime is unavailable: %s\\n' in text
    assert 'Current source CLI is unavailable: %s\\n' in text
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


def test_uninstall_dry_run_is_available_without_root_or_installed_files():
    result = subprocess.run(
        [
            "bash",
            str(UNINSTALL),
            "--dry-run",
            "--root",
            "/mnt/TestPool/TruePanel",
        ],
        check=False,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "== TruePanel Uninstall Dry Run ==" in result.stdout
    assert "Install root:" in result.stdout
    assert "/mnt/TestPool/TruePanel" in result.stdout
    assert "truepanel-host-agent.service" in result.stdout
    assert "Host ownership lease must be released" in result.stdout
    assert "Motherboard fan control must verify Automatic" in result.stdout
    assert (
        "DRY RUN ONLY: no services were stopped, "
        "no fan state changed, no files were removed."
        in result.stdout
    )


def test_uninstall_dry_run_exits_before_any_mutating_path():
    text = source()

    dry_run = text.index('if [[ "$DRY_RUN" -eq 1 ]]')
    dry_run_exit = text.index("exit 0", dry_run)
    root_gate = text.index('if [[ $EUID -ne 0 ]]')
    uninstaller = text.index('echo "== TruePanel Uninstaller =="')
    first_stop = text.index(
        'stop_service "$HOST_AGENT_SERVICE_NAME"',
        uninstaller,
    )
    ownership = text.index(
        "assert_host_ownership_released",
        uninstaller,
    )
    fan_safety = text.index(
        "verify_fan_safety",
        uninstaller,
    )
    first_remove = text.index("rm -f", uninstaller)

    assert dry_run < dry_run_exit < root_gate
    assert dry_run_exit < uninstaller
    assert dry_run_exit < first_stop
    assert dry_run_exit < ownership
    assert dry_run_exit < fan_safety
    assert dry_run_exit < first_remove


def test_uninstall_dry_run_plan_contains_no_mutating_commands():
    text = source()
    start = text.index("print_uninstall_plan()")
    end = text.index("\n}\n", start)
    block = text[start:end]

    for forbidden in (
        "systemctl stop",
        "systemctl disable",
        "systemctl daemon-reload",
        "rm -f",
        "rm -rf",
        "rmdir ",
        "verify_fan_safety",
        "assert_host_ownership_released",
        "flock",
    ):
        assert forbidden not in block


def test_uninstall_usage_documents_dry_run():
    text = source()

    assert "[--dry-run]" in text
    assert "--dry-run)" in text
