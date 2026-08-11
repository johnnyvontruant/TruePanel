from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def script_source(name):
    return (
        ROOT / name
    ).read_text(
        encoding="utf-8"
    )


def test_start_script_restores_both_services():
    source = script_source(
        "start-truepanel.sh"
    )

    assert "truepanel.service" in source
    assert (
        "truepanel-mission-control.service"
        in source
    )
    assert "daemon-reload" in source
    assert "systemctl" in source
    assert "enable" in source
    assert "restart" in source


def test_start_script_uses_its_own_install_root():
    source = script_source(
        "start-truepanel.sh"
    )

    assert 'dirname -- "${BASH_SOURCE[0]}"' in source
    assert "WorkingDirectory=$ROOT_DIR" in source
    assert "$ROOT_DIR/truepanel.py run" in source
    assert "$ROOT_DIR/truepanel.yaml" in source
    assert "/opt/truepanel" not in source


def test_start_script_supports_safe_sandbox_mode():
    source = script_source(
        "start-truepanel.sh"
    )

    assert "TRUEPANEL_SYSTEMD_DIR" in source
    assert "TRUEPANEL_ENV_DIR" in source
    assert "TRUEPANEL_SKIP_SYSTEMCTL" in source
    assert "Systemctl actions skipped" in source


def test_start_script_preserves_existing_environment():
    source = script_source(
        "start-truepanel.sh"
    )

    assert 'if [[ ! -f "$MISSION_ENV_FILE" ]]' in source
    assert "Preserved Mission Control environment" in source
    assert "TRUEPANEL_MC_HOST=0.0.0.0" in source
    assert "TRUEPANEL_MC_PORT=8787" in source


def test_deploy_script_preserves_runtime_state():
    source = script_source(
        "deploy-truenas.sh"
    )

    for exclusion in (
        "--exclude='.venv/'",
        "--exclude='truepanel.yaml'",
        "--exclude='development/logs/'",
        "--exclude='development/firmware/lab/'",
    ):
        assert exclusion in source

    assert "--delete" in source
    assert "start-truepanel.sh" in source


def test_deploy_script_requires_explicit_restart():
    source = script_source(
        "deploy-truenas.sh"
    )

    assert 'RESTART=false' in source
    assert '--restart)' in source
    assert 'RESTART=true' in source
    assert 'if [[ "$RESTART" == "true" ]]' in source


def test_deploy_script_discovers_installed_root():
    source = script_source(
        "deploy-truenas.sh"
    )

    assert "TRUEPANEL_DEPLOY_ROOT" in source
    assert (
        "systemctl show truepanel.service"
        in source
    )
    assert "WorkingDirectory" in source
    assert (
        "/mnt/SSDs/Applications/TruePanel"
        not in source
    )


def test_deploy_script_fails_without_safe_target():
    source = script_source(
        "deploy-truenas.sh"
    )

    assert (
        "Could not determine the deployed "
        "TruePanel root."
        in source
    )
    assert (
        "Set TRUEPANEL_DEPLOY_ROOT"
        in source
    )


def test_deploy_script_supports_dry_run():
    source = script_source(
        "deploy-truenas.sh"
    )

    assert 'DRY_RUN=false' in source
    assert '--dry-run)' in source
    assert '--itemize-changes' in source
    assert (
        "Deployment preview complete; "
        "no files were changed."
        in source
    )
