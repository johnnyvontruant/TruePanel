from pathlib import Path


def installer_source():
    return Path("install.sh").read_text(encoding="utf-8")


def test_installer_defines_mission_control_paths():
    source = installer_source()
    assert "MISSION_CONTROL_SERVICE_FILE=" in source
    assert "/etc/systemd/system/truepanel-mission-control.service" in source
    assert "MISSION_CONTROL_ENV_FILE=" in source
    assert "/etc/default/truepanel-mission-control" in source


def test_installer_installs_companion_service():
    source = installer_source()
    assert "packaging/systemd/truepanel-mission-control.service" in source
    assert "\"$MISSION_CONTROL_SERVICE_FILE\"" in source


def test_installer_preserves_existing_environment():
    source = installer_source()
    assert "if [ ! -f \"$MISSION_CONTROL_ENV_FILE\" ]; then" in source
    assert "Preserving existing Mission Control environment:" in source


def test_installer_leaves_service_disabled():
    source = installer_source()
    assert "Mission Control is installed but remains disabled by default." in source
    assert "systemctl enable truepanel-mission-control" in source
    assert "systemctl enable --now truepanel-mission-control" not in source
    assert "systemctl start truepanel-mission-control" in source


def test_installer_documents_safe_defaults():
    source = installer_source()
    assert "http://127.0.0.1:8787" in source
    assert "TRUEPANEL_MC_HOST=0.0.0.0" in source
    assert "TRUEPANEL_MC_ALLOW_CONFIG_WRITES=true" in source
