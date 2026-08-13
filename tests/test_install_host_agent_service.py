from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(name):
    return (ROOT / name).read_text(
        encoding="utf-8"
    )


def service_heredoc(text, variable):
    marker = f'cat > "${variable}" <<SERVICE\n'
    start = text.index(marker) + len(marker)
    end = text.index("\nSERVICE\n", start)
    return text[start:end]


def test_fresh_install_lays_down_dormant_host_agent_unit():
    install = source("install.sh")
    unit = service_heredoc(
        install,
        "HOST_AGENT_SERVICE_FILE",
    )

    assert (
        'HOST_AGENT_SERVICE_FILE='
        '"/etc/systemd/system/truepanel-host-agent.service"'
        in install
    )
    assert (
        "Description=TruePanel Privileged Host Agent "
        "(standalone activation locked)"
        in unit
    )
    assert (
        "ConditionPathExists=/run/truepanel/"
        "standalone-host-agent.enabled"
        in unit
    )
    assert (
        "ExecStart=$PYTHON_BIN -m truepanel.host.agent"
        in unit
    )
    assert "[Install]" not in unit


def test_install_and_start_paths_share_host_agent_safety_contract():
    install_unit = service_heredoc(
        source("install.sh"),
        "HOST_AGENT_SERVICE_FILE",
    )
    start_unit = service_heredoc(
        source("start-truepanel.sh"),
        "HOST_AGENT_SERVICE_FILE",
    )

    for contract in (
        "Description=TruePanel Privileged Host Agent "
        "(standalone activation locked)",
        "After=local-fs.target",
        "ConditionPathExists=/run/truepanel/"
        "standalone-host-agent.enabled",
        "ExecStart=$PYTHON_BIN -m truepanel.host.agent",
        "Restart=on-failure",
        "RestartSec=5",
        "TimeoutStopSec=15",
        "UMask=0027",
    ):
        assert contract in install_unit
        assert contract in start_unit

    assert "[Install]" not in install_unit
    assert "[Install]" not in start_unit


def test_fresh_install_never_enables_or_starts_host_agent():
    install = source("install.sh")

    assert (
        "Standalone Host Agent activation remains locked; "
        "unit was not enabled or started."
        in install
    )
    assert (
        "systemctl enable truepanel-host-agent"
        not in install
    )
    assert (
        "systemctl start truepanel-host-agent"
        not in install
    )
    assert (
        "systemctl restart truepanel-host-agent"
        not in install
    )


def test_install_dry_run_is_available_without_root_or_target_tree():
    import subprocess

    install = ROOT / "install.sh"
    result = subprocess.run(
        [
            "bash",
            str(install),
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
    assert "== TruePanel Install Dry Run ==" in result.stdout
    assert "/mnt/TestPool/TruePanel" in result.stdout
    assert "truepanel-host-agent.service" in result.stdout
    assert "Keep standalone Host Agent activation locked" in result.stdout
    assert "does not start or enable TruePanel services" in result.stdout
    assert (
        "DRY RUN ONLY: no directories were created, "
        "no files were copied or written, no dependencies were installed, "
        "no services were changed."
        in result.stdout
    )


def test_install_dry_run_exits_before_root_and_mutating_actions():
    text = source("install.sh")

    dry_run = text.index('if [[ "$DRY_RUN" -eq 1 ]]')
    dry_run_exit = text.index("exit 0", dry_run)
    root_gate = text.index('if [[ "$(id -u)" -ne 0 ]]')
    first_mkdir = text.index('mkdir -p -- "$INSTALL_DIR"')
    first_rsync = text.index("rsync -a --delete")
    first_service_write = text.index(
        'cat > "$MISSION_CONTROL_SERVICE_FILE"'
    )
    daemon_reload = text.index("systemctl daemon-reload")

    assert dry_run < dry_run_exit < root_gate
    assert dry_run_exit < first_mkdir
    assert dry_run_exit < first_rsync
    assert dry_run_exit < first_service_write
    assert dry_run_exit < daemon_reload


def test_install_dry_run_plan_contains_no_mutating_commands():
    text = source("install.sh")
    start = text.index("print_install_plan()")
    end = text.index("\n}\n", start)
    block = text[start:end]

    for forbidden in (
        "mkdir ",
        "rsync ",
        "pip install",
        "cat >",
        "chmod ",
        "systemctl daemon-reload",
        "systemctl start",
        "systemctl enable",
        "rm ",
    ):
        assert forbidden not in block


def test_install_usage_documents_dry_run():
    text = source("install.sh")

    assert "[--dry-run]" in text
    assert "--dry-run)" in text


def test_install_bootstraps_pipless_venv_without_system_runtime_fallback():
    text = source("install.sh")

    assert 'PIP_BOOTSTRAP_VERSION="26.2.1"' in text
    assert (
        'PIP_BOOTSTRAP_SHA256="'
        '71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e"'
        in text
    )
    assert "python3 -m venv --without-pip" in text
    assert "urllib.request.urlopen(url, timeout=60)" in text
    assert "hashlib.sha256(payload).hexdigest()" in text
    assert 'PYTHONPATH="$PIP_BOOTSTRAP_WHEEL"' in text
    assert 'PIP_RUNNER=(env "PYTHONPATH=$PIP_BOOTSTRAP_WHEEL"' in text
    assert "Using system Python instead." not in text
    assert 'PYTHON_BIN="$(command -v python3)"' not in text


def test_install_checks_all_runtime_dependencies_before_service_writes():
    text = source("install.sh")

    check = text.index("required = {")
    cli_write = text.index('echo "Creating CLI directory..."')
    mission_write = text.index(
        'cat > "$MISSION_CONTROL_SERVICE_FILE"'
    )
    runtime_check = text[check:cli_write]

    assert '"serial": "pyserial"' in runtime_check
    assert '"psutil": "psutil"' in runtime_check
    assert '"yaml": "PyYAML"' in runtime_check
    assert check < cli_write < mission_write


def test_install_docs_keep_dependencies_out_of_system_python():
    text = source("docs/INSTALLATION.md")

    assert "pinned, hash-verified pip wheel" in text
    assert "does not install TruePanel dependencies into system Python" in text
