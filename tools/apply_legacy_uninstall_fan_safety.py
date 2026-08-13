from pathlib import Path

uninstall = Path("uninstall.sh")
text = uninstall.read_text(encoding="utf-8")

anchor = "set -euo pipefail\n\nINSTALL_DIR=\"${TRUEPANEL_INSTALL_ROOT:-}\""
replacement = """set -euo pipefail

SCRIPT_DIR=\"$(cd -- \"$(dirname -- \"${BASH_SOURCE[0]}\")\" && pwd)\"
SOURCE_CLI=\"$SCRIPT_DIR/truepanel.py\"

INSTALL_DIR=\"${TRUEPANEL_INSTALL_ROOT:-}\""" 
if anchor not in text:
    raise SystemExit("missing script-dir anchor")
text = text.replace(anchor, replacement, 1)

anchor = """  if [[ ! -x \"$BIN_FILE\" ]]
  then
    printf 'TruePanel CLI wrapper is unavailable: %s\\n' \\
      \"$BIN_FILE\" >&2
    printf '%s\\n' \\
      'Refusing uninstall because fan restoration cannot be verified.' \\
      >&2
    exit 1
  fi

  echo \"Verifying motherboard fan-control restoration...\"

  if ! \"$BIN_FILE\" host fan-safety \\
    --config \"$CONFIG_FILE\"
"""
replacement = """  local verifier=()

  if [[ -x \"$BIN_FILE\" ]]
  then
    verifier=(\"$BIN_FILE\")
  elif [[ -x \"$VENV_PYTHON\" && -f \"$SOURCE_CLI\" ]]
  then
    printf '%s\\n' \\
      'Installed CLI wrapper unavailable; using current source CLI with installed runtime.'
    verifier=(\"$VENV_PYTHON\" \"$SOURCE_CLI\")
  else
    printf 'TruePanel CLI wrapper is unavailable: %s\\n' \\
      \"$BIN_FILE\" >&2
    printf 'Legacy Python runtime is unavailable: %s\\n' \\
      \"$VENV_PYTHON\" >&2
    printf 'Current source CLI is unavailable: %s\\n' \\
      \"$SOURCE_CLI\" >&2
    printf '%s\\n' \\
      'Refusing uninstall because fan restoration cannot be verified.' \\
      >&2
    exit 1
  fi

  echo \"Verifying motherboard fan-control restoration...\"

  if ! \"${verifier[@]}\" host fan-safety \\
    --config \"$CONFIG_FILE\"
"""
if anchor not in text:
    raise SystemExit("missing fan verifier anchor")
text = text.replace(anchor, replacement, 1)

anchor = """BIN_FILE=\"$INSTALL_DIR/bin/truepanel\"
CONFIG_FILE=\"$INSTALL_DIR/truepanel.yaml\"
"""
replacement = """BIN_FILE=\"$INSTALL_DIR/bin/truepanel\"
VENV_PYTHON=\"$INSTALL_DIR/.venv/bin/python\"
CONFIG_FILE=\"$INSTALL_DIR/truepanel.yaml\"
"""
if anchor not in text:
    raise SystemExit("missing install-path anchor")
text = text.replace(anchor, replacement, 1)

uninstall.write_text(text, encoding="utf-8")

tests = Path("tests/test_uninstall_host_cleanup.py")
text = tests.read_text(encoding="utf-8")

old = """    assert 'CONFIG_FILE=\"$INSTALL_DIR/truepanel.yaml\"' in text
    assert '\"$BIN_FILE\" host fan-safety' in text
    assert '--config \"$CONFIG_FILE\"' in text


def test_uninstall_refuses_fan_verification_without_config_or_cli():
    text = source()

    assert '[[ ! -f \"$CONFIG_FILE\" ]]' in text
    assert '[[ ! -x \"$BIN_FILE\" ]]' in text
    assert (
        \"Refusing uninstall because fan restoration cannot be verified.\"
        in text
    )
"""
new = """    assert 'CONFIG_FILE=\"$INSTALL_DIR/truepanel.yaml\"' in text
    assert '\"${verifier[@]}\" host fan-safety' in text
    assert '--config \"$CONFIG_FILE\"' in text


def test_uninstall_supports_legacy_fan_safety_without_installed_wrapper():
    text = source()

    assert 'SOURCE_CLI=\"$SCRIPT_DIR/truepanel.py\"' in text
    assert 'VENV_PYTHON=\"$INSTALL_DIR/.venv/bin/python\"' in text
    assert '[[ -x \"$BIN_FILE\" ]]' in text
    assert (
        '[[ -x \"$VENV_PYTHON\" && -f \"$SOURCE_CLI\" ]]'
        in text
    )
    assert 'verifier=(\"$BIN_FILE\")' in text
    assert (
        'verifier=(\"$VENV_PYTHON\" \"$SOURCE_CLI\")'
        in text
    )
    assert (
        \"Installed CLI wrapper unavailable; using current source CLI \"
        \"with installed runtime.\"
        in text
    )


def test_uninstall_refuses_fan_verification_without_config_or_any_cli_path():
    text = source()

    assert '[[ ! -f \"$CONFIG_FILE\" ]]' in text
    assert 'Legacy Python runtime is unavailable: %s\\n' in text
    assert 'Current source CLI is unavailable: %s\\n' in text
    assert (
        \"Refusing uninstall because fan restoration cannot be verified.\"
        in text
    )
"""
if old not in text:
    raise SystemExit("missing uninstall test anchor")
text = text.replace(old, new, 1)

tests.write_text(text, encoding="utf-8")
