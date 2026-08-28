from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy-truenas.sh"


def test_deploy_preserves_install_managed_bin_directory():
    source = DEPLOY.read_text(encoding="utf-8")

    assert "--delete" in source
    assert "--exclude='bin/'" in source
    assert "--exclude='truepanel.yaml'" in source


def test_deploy_repairs_cli_wrapper_after_real_sync():
    source = DEPLOY.read_text(encoding="utf-8")

    assert 'install -d -m 0755 "$DEPLOYED_ROOT/bin"' in source
    assert 'cat > "$DEPLOYED_ROOT/bin/truepanel"' in source
    assert 'chmod 0755 "$DEPLOYED_ROOT/bin/truepanel"' in source
    assert 'exec "$PYTHON_BIN" "$ROOT_DIR/truepanel.py" "$@"' in source


def test_dry_run_exits_before_wrapper_mutation():
    source = DEPLOY.read_text(encoding="utf-8")

    dry_run_exit = source.index(
        "Deployment preview complete; no files were changed."
    )
    wrapper_install = source.index(
        'install -d -m 0755 "$DEPLOYED_ROOT/bin"'
    )

    assert dry_run_exit < wrapper_install
