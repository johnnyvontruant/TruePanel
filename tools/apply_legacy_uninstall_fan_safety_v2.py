from pathlib import Path

uninstall = Path("uninstall.sh")
text = uninstall.read_text(encoding="utf-8")

marker = "set -euo pipefail\n"
insert = r'''set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_CLI="$SCRIPT_DIR/truepanel.py"
'''
if text.count(marker) != 1:
    raise SystemExit("unexpected shell prologue")
text = text.replace(marker, insert, 1)

path_marker = 'BIN_FILE="$INSTALL_DIR/bin/truepanel"\n'
path_insert = (
    'BIN_FILE="$INSTALL_DIR/bin/truepanel"\n'
    'VENV_PYTHON="$INSTALL_DIR/.venv/bin/python"\n'
)
if text.count(path_marker) != 1:
    raise SystemExit("unexpected CLI path assignment")
text = text.replace(path_marker, path_insert, 1)

function_start = text.index("verify_fan_safety()")
start = text.index('  if [[ ! -x "$BIN_FILE" ]]', function_start)
old_call = r'''  if ! "$BIN_FILE" host fan-safety \
    --config "$CONFIG_FILE"
'''
end = text.index(old_call, start) + len(old_call)

new_block = r'''  local verifier=()

  if [[ -x "$BIN_FILE" ]]
  then
    verifier=("$BIN_FILE")
  elif [[ -x "$VENV_PYTHON" && -f "$SOURCE_CLI" ]]
  then
    printf '%s\n' \
      'Installed CLI wrapper unavailable; using current source CLI with installed runtime.'
    verifier=("$VENV_PYTHON" "$SOURCE_CLI")
  else
    printf 'TruePanel CLI wrapper is unavailable: %s\n' \
      "$BIN_FILE" >&2
    printf 'Legacy Python runtime is unavailable: %s\n' \
      "$VENV_PYTHON" >&2
    printf 'Current source CLI is unavailable: %s\n' \
      "$SOURCE_CLI" >&2
    printf '%s\n' \
      'Refusing uninstall because fan restoration cannot be verified.' \
      >&2
    exit 1
  fi

  echo "Verifying motherboard fan-control restoration..."

  if ! "${verifier[@]}" host fan-safety \
    --config "$CONFIG_FILE"
'''
text = text[:start] + new_block + text[end:]
uninstall.write_text(text, encoding="utf-8")

tests = Path("tests/test_uninstall_host_cleanup.py")
text = tests.read_text(encoding="utf-8")

old_assert = '    assert \'"$BIN_FILE" host fan-safety\' in text\n'
new_assert = '    assert \'"${verifier[@]}" host fan-safety\' in text\n'
if text.count(old_assert) != 1:
    raise SystemExit("unexpected fan-safety invocation assertion")
text = text.replace(old_assert, new_assert, 1)

start_name = "def test_uninstall_refuses_fan_verification_without_config_or_cli():"
next_name = "def test_uninstall_preserves_install_for_diagnosis_when_fan_safety_fails():"
start = text.index(start_name)
end = text.index(next_name, start)

new_tests = r'''def test_uninstall_supports_legacy_fan_safety_without_installed_wrapper():
    text = source()

    assert 'SOURCE_CLI="$SCRIPT_DIR/truepanel.py"' in text
    assert 'VENV_PYTHON="$INSTALL_DIR/.venv/bin/python"' in text
    assert '[[ -x "$BIN_FILE" ]]' in text
    assert (
        '[[ -x "$VENV_PYTHON" && -f "$SOURCE_CLI" ]]'
        in text
    )
    assert 'verifier=("$BIN_FILE")' in text
    assert (
        'verifier=("$VENV_PYTHON" "$SOURCE_CLI")'
        in text
    )
    assert (
        "Installed CLI wrapper unavailable; using current source CLI "
        "with installed runtime."
        in text
    )


def test_uninstall_refuses_fan_verification_without_config_or_any_cli_path():
    text = source()

    assert '[[ ! -f "$CONFIG_FILE" ]]' in text
    assert 'Legacy Python runtime is unavailable: %s\\n' in text
    assert 'Current source CLI is unavailable: %s\\n' in text
    assert (
        "Refusing uninstall because fan restoration cannot be verified."
        in text
    )


'''
text = text[:start] + new_tests + text[end:]
tests.write_text(text, encoding="utf-8")
