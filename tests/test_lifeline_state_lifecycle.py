from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(name):
    return (ROOT / name).read_text(encoding="utf-8")


def service_heredoc(script, variable):
    marker = f'cat > "${variable}" <<SERVICE\n'
    start = script.index(marker) + len(marker)
    end = script.index("\nSERVICE\n", start)
    return script[start:end]


def test_mission_control_declares_private_persistent_state_directory():
    cases = (
        ("install.sh", "MISSION_CONTROL_SERVICE_FILE"),
        ("start-truepanel.sh", "MISSION_SERVICE_FILE"),
    )

    for filename, variable in cases:
        unit = service_heredoc(
            source(filename),
            variable,
        )

        assert "StateDirectory=truepanel" in unit
        assert "StateDirectoryMode=0700" in unit
        assert "PrivateTmp=true" in unit
        assert "UMask=0027" in unit


def test_fingerprint_default_path_lives_inside_managed_state_directory():
    fingerprint = source(
        "truepanel/lifeline/fingerprint.py"
    )

    assert (
        '"/var/lib/truepanel/lifeline/drive-fingerprints.json"'
        in fingerprint
    )


def test_install_dry_run_documents_persistent_state_contract():
    installer = source("install.sh")

    assert (
        "Declare private persistent Mission Control state: "
        "/var/lib/truepanel (mode 0700)"
        in installer
    )


def test_uninstall_removes_lifeline_metadata_after_safety_gates():
    uninstaller = source("uninstall.sh")

    assert (
        'PERSISTENT_STATE_DIR="/var/lib/truepanel"'
        in uninstaller
    )
    assert (
        'LIFELINE_STATE_DIR="$PERSISTENT_STATE_DIR/lifeline"'
        in uninstaller
    )
    assert (
        'rm -rf -- "$LIFELINE_STATE_DIR"'
        in uninstaller
    )
    assert (
        'rmdir "$PERSISTENT_STATE_DIR" 2>/dev/null || true'
        in uninstaller
    )

    # Never recursively remove the shared TruePanel state root. Future
    # persistent features may own sibling state under /var/lib/truepanel.
    assert (
        'rm -rf -- "$PERSISTENT_STATE_DIR"'
        not in uninstaller
    )

    fan_gate = uninstaller.index(
        "verify_fan_safety\n"
    )
    metadata_cleanup = uninstaller.index(
        'rm -rf -- "$LIFELINE_STATE_DIR"'
    )

    assert metadata_cleanup > fan_gate


def test_uninstall_dry_run_discloses_metadata_removal():
    uninstaller = source("uninstall.sh")

    assert (
        "Persistent Lifeline metadata that would be removed:"
        in uninstaller
    )
    assert "$LIFELINE_STATE_DIR" in uninstaller
    assert "$PERSISTENT_STATE_DIR (when empty)" in uninstaller
