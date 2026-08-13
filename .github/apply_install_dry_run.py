from pathlib import Path


install = Path("install.sh")
text = install.read_text(encoding="utf-8")

old = 'INSTALL_DIR="${TRUEPANEL_INSTALL_ROOT:-}"\n'
new = old + 'DRY_RUN=0\n'
assert text.count(old) == 1
text = text.replace(old, new, 1)

old = """usage() {
  printf 'Usage: %s --root /mnt/POOL/DATASET/TruePanel\\n' "$0"
  printf '       TRUEPANEL_INSTALL_ROOT=/mnt/POOL/DATASET/TruePanel %s\\n' "$0"
}
"""
new = """usage() {
  printf 'Usage: %s [--dry-run] --root /mnt/POOL/DATASET/TruePanel\\n' "$0"
  printf '       TRUEPANEL_INSTALL_ROOT=/mnt/POOL/DATASET/TruePanel %s [--dry-run]\\n' "$0"
}

print_install_plan() {
  local bin_file="$INSTALL_DIR/bin/truepanel"

  cat <<EOF
== TruePanel Install Dry Run ==

Source tree:
  $SOURCE_ROOT

Install root:
  $INSTALL_DIR

Actions a real install would perform:
  Validate prerequisites: python3, rsync, systemctl
  Create/preserve install root and synchronize the source tree
  Create truepanel.yaml only when it does not already exist
  Create a Python virtual environment when supported and install requirements
  Create CLI wrapper: $bin_file
  Install LCD service: $SERVICE_FILE
  Install Mission Control service: $MISSION_CONTROL_SERVICE_FILE
  Create/preserve Mission Control environment: $MISSION_CONTROL_ENV_FILE
  Install dormant Host Agent service: $HOST_AGENT_SERVICE_FILE
  Keep standalone Host Agent activation locked and do not start it
  Reload systemd daemon state
  Run TruePanel Doctor from the installed tree

The installer does not start or enable TruePanel services automatically.

DRY RUN ONLY: no directories were created, no files were copied or written, no dependencies were installed, no services were changed.
EOF
}
"""
assert text.count(old) == 1
text = text.replace(old, new, 1)

old = """    -h|--help)
      usage
      exit 0
      ;;
"""
new = """    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
"""
assert text.count(old) == 1
text = text.replace(old, new, 1)

anchor = """if [[ "$(id -u)" -ne 0 ]]
then
"""
block = """if [[ "$DRY_RUN" -eq 1 ]]
then
  print_install_plan
  exit 0
fi

"""
assert text.count(anchor) == 1
text = text.replace(anchor, block + anchor, 1)
install.write_text(text, encoding="utf-8")


tests = Path("tests/test_install_host_agent_service.py")
test_text = tests.read_text(encoding="utf-8")
addition = r'''


def test_install_dry_run_is_available_without_root_or_target_tree():
    import subprocess

    install = ROOT / "install.sh"
    result = subprocess.run(
        [
            "bash",
            str(install),
            "--dry-run",
            "--root",
            "/mnt/TestPool/TruePanel",
        ],
        check=False,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "== TruePanel Install Dry Run ==" in result.stdout
    assert "/mnt/TestPool/TruePanel" in result.stdout
    assert "truepanel-host-agent.service" in result.stdout
    assert "Keep standalone Host Agent activation locked" in result.stdout
    assert "does not start or enable TruePanel services" in result.stdout
    assert (
        "DRY RUN ONLY: no directories were created, "
        "no files were copied or written, no dependencies were installed, "
        "no services were changed."
        in result.stdout
    )


def test_install_dry_run_exits_before_root_and_mutating_actions():
    text = source("install.sh")

    dry_run = text.index('if [[ "$DRY_RUN" -eq 1 ]]')
    dry_run_exit = text.index("exit 0", dry_run)
    root_gate = text.index('if [[ "$(id -u)" -ne 0 ]]')
    first_mkdir = text.index('mkdir -p -- "$INSTALL_DIR"')
    first_rsync = text.index("rsync -a --delete")
    first_service_write = text.index(
        'cat > "$MISSION_CONTROL_SERVICE_FILE"'
    )
    daemon_reload = text.index("systemctl daemon-reload")

    assert dry_run < dry_run_exit < root_gate
    assert dry_run_exit < first_mkdir
    assert dry_run_exit < first_rsync
    assert dry_run_exit < first_service_write
    assert dry_run_exit < daemon_reload


def test_install_dry_run_plan_contains_no_mutating_commands():
    text = source("install.sh")
    start = text.index("print_install_plan()")
    end = text.index("\n}\n", start)
    block = text[start:end]

    for forbidden in (
        "mkdir ",
        "rsync ",
        "pip install",
        "cat >",
        "chmod ",
        "systemctl daemon-reload",
        "systemctl start",
        "systemctl enable",
        "rm ",
    ):
        assert forbidden not in block


def test_install_usage_documents_dry_run():
    text = source("install.sh")

    assert "[--dry-run]" in text
    assert "--dry-run)" in text
'''
assert "def test_install_dry_run_is_available_without_root_or_target_tree():" not in test_text
tests.write_text(test_text.rstrip() + addition, encoding="utf-8")
