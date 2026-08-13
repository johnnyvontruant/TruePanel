from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"
RUNBOOK = ROOT / "docs" / "CLEAN_INSTALL_VALIDATION.md"


def source():
    return INSTALL.read_text(encoding="utf-8")


def rsync_block():
    text = source()
    start = text.index("rsync -a --delete")
    end_marker = '  "$SOURCE_ROOT/" "$INSTALL_DIR/"'
    end = text.index(end_marker, start) + len(end_marker)
    return text[start:end]


def default_config_block():
    text = source()
    marker = 'cat > "$INSTALL_DIR/truepanel.yaml" <<\'YAML\'\n'
    start = text.index(marker) + len(marker)
    end = text.index("\nYAML\n", start)
    return text[start:end]


def test_installer_never_syncs_source_local_or_machine_state():
    block = rsync_block()

    for excluded in (
        ".git",
        ".env",
        ".venv",
        "venv",
        ".quality-venv",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "*.pyc",
        "*.egg-info",
        "truepanel.yaml",
        "truepanel.backup-*",
        "var/history",
        "development/logs",
        "development/backups",
        "plugins/.truepanel-plugin-state.json",
    ):
        assert f'--exclude "{excluded}"' in block


def test_installer_preserves_target_config_before_defaulting():
    text = source()
    sync = text.index("rsync -a --delete")
    exclusion = text.index(
        '--exclude "truepanel.yaml"',
        sync,
    )
    default = text.index(
        'if [ ! -f "$INSTALL_DIR/truepanel.yaml" ]'
    )

    assert sync < exclusion < default


def test_installer_generated_default_has_no_hardware_authority():
    block = default_config_block()

    for forbidden in (
        "fan_control:",
        "storage_topology:",
        "thermal_policy:",
        "controlled_channels:",
        "/sys/class/hwmon/",
        "serial:",
    ):
        assert forbidden not in block

    assert "theme_pack: default" in block
    assert "flightdeck:" in block


def test_install_preview_explains_source_state_isolation():
    text = source()
    start = text.index("print_install_plan()")
    end = text.index("\n}\n", start)
    block = text[start:end]

    assert "synchronize only managed source files" in block
    assert "Exclude source-local config" in block
    assert "Preserve an existing target truepanel.yaml" in block
    assert "safe default" in block


def test_clean_install_runbook_requires_generic_fresh_config():
    text = RUNBOOK.read_text(encoding="utf-8")
    phase_4 = text.index("## Phase 4: Fresh install")
    phase_5 = text.index(
        "## Phase 5: Immediate post-install verification"
    )
    block = text[phase_4:phase_5]

    assert "must **not** import `truepanel.yaml`" in block
    assert "Source-local state is excluded" in block
    assert "generic safe `truepanel.yaml`" in block
    assert "machine-specific source configuration" in block
