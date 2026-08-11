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

    assert (
        'cat > "$MISSION_CONTROL_SERVICE_FILE"'
        in source
    )
    assert "WorkingDirectory=$INSTALL_DIR" in source
    assert (
        "ExecStart=$PYTHON_BIN "
        "-m truepanel.web.service"
        in source
    )


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


def test_installer_requires_persistent_install_root():
    source = installer_source()

    assert "TRUEPANEL_INSTALL_ROOT" in source
    assert "--root" in source
    assert (
        "No persistent TruePanel installation root "
        "was provided."
        in source
    )
    assert "/opt/truepanel" not in source


def test_installer_can_discover_existing_installation():
    source = installer_source()

    assert (
        "systemctl show truepanel.service"
        in source
    )
    assert "WorkingDirectory" in source


def test_installer_uses_its_own_source_tree():
    source = installer_source()

    assert 'dirname -- "${BASH_SOURCE[0]}"' in source
    assert '"$SOURCE_ROOT/" "$INSTALL_DIR/"' in source


def test_installer_checks_root_before_creating_installation():
    source = installer_source()

    root_check = source.index(
        'if [[ "$(id -u)" -ne 0 ]]'
    )
    mkdir_install = source.index(
        'mkdir -p -- "$INSTALL_DIR"'
    )

    assert root_check < mkdir_install


def uninstaller_source():
    return Path("uninstall.sh").read_text(
        encoding="utf-8"
    )


def test_uninstaller_uses_portable_install_root():
    source = uninstaller_source()

    assert "TRUEPANEL_INSTALL_ROOT" in source
    assert "--root" in source
    assert (
        "systemctl show truepanel.service"
        in source
    )
    assert "/opt/truepanel" not in source


def test_uninstaller_refuses_unknown_root():
    source = uninstaller_source()

    assert (
        "Could not determine the TruePanel "
        "installation root."
        in source
    )
