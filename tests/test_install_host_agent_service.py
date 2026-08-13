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
