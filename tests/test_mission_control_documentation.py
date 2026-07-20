from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path):
    return (ROOT / relative_path).read_text(
        encoding="utf-8"
    )


def test_installation_documents_safe_defaults():
    text = read("docs/INSTALLATION.md")

    assert "TRUEPANEL_MC_HOST=127.0.0.1" in text
    assert "TRUEPANEL_MC_ALLOW_CONFIG_WRITES=false" in text
    assert "never writes directly to the LCD serial interface" in text


def test_cli_documents_operator_commands():
    text = read("docs/CLI.md")

    for command in (
        "truepanel mission-control status",
        "truepanel mission-control start",
        "truepanel mission-control stop",
        "truepanel mission-control restart",
        "truepanel mission-control logs",
    ):
        assert command in text


def test_upgrade_guide_preserves_live_configuration():
    text = read("docs/UPGRADING.md")

    assert "/opt/truepanel/truepanel.yaml" in text
    assert "/etc/default/truepanel-mission-control" in text
    assert "primary LCD service" in text


def test_architecture_documents_hardware_boundary():
    text = read("docs/ARCHITECTURE.md")

    assert "HTTP handlers do not directly operate" in text
    assert "sysfs" in text
    assert "Files are replaced atomically" in text
    assert "primary LCD service is not automatically restarted" in text


def test_readme_exposes_mission_control():
    text = read("README.md")

    assert "truepanel mission-control status" in text
    assert "localhost-bound and read-only by default" in text
