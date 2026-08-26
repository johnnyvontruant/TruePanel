from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_startup_provisions_private_recovery_state_directories():
    script = (ROOT / "start-truepanel.sh").read_text(encoding="utf-8")

    assert (
        "StateDirectory=truepanel/lifeline truepanel/pathfinder"
        in script
    )
    assert "StateDirectoryMode=0700" in script


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
    assert 'chmod -R' not in script
