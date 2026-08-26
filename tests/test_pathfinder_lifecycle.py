from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_install_and_startup_provision_private_recovery_state_directories():
    for filename in ("install.sh", "start-truepanel.sh"):
        script = (ROOT / filename).read_text(encoding="utf-8")

        assert (
            "StateDirectory=truepanel/lifeline truepanel/pathfinder"
            in script
        )
        assert "StateDirectoryMode=0700" in script
        assert "StateDirectory=truepanel\n" not in script


def test_installer_documents_both_private_recovery_state_directories():
    script = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert (
        "Declare private persistent Lifeline state: "
        "/var/lib/truepanel/lifeline (mode 0700)"
        in script
    )
    assert (
        "Declare private persistent Pathfinder state: "
        "/var/lib/truepanel/pathfinder (mode 0700)"
        in script
    )


def test_uninstall_cleans_private_recovery_state_only():
    script = (ROOT / "uninstall.sh").read_text(encoding="utf-8")

    assert (
        'LIFELINE_STATE_DIR="$PERSISTENT_STATE_DIR/lifeline"'
        in script
    )
    assert (
        'PATHFINDER_STATE_DIR="$PERSISTENT_STATE_DIR/pathfinder"'
        in script
    )
    assert (
        'rm -rf -- "$LIFELINE_STATE_DIR" "$PATHFINDER_STATE_DIR"'
        in script
    )
    assert 'rm -rf -- "$PERSISTENT_STATE_DIR"' not in script
    assert 'rmdir "$PERSISTENT_STATE_DIR" 2>/dev/null || true' in script
    assert 'chmod -R' not in script
