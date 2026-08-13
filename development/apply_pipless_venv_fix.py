from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"
TESTS = ROOT / "tests/test_install_host_agent_service.py"
DOCS = ROOT / "docs/INSTALLATION.md"


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match, found {count}")
    return text.replace(old, new, 1)


install = INSTALL.read_text(encoding="utf-8")
install = replace_once(
    install,
    'PYTHON_BIN=""\n',
    'PYTHON_BIN=""\n'
    'PIP_BOOTSTRAP_VERSION="26.2.1"\n'
    'PIP_BOOTSTRAP_URL="https://files.pythonhosted.org/packages/f3/6e/'
    '1736e5b4ae2b778ef2f81c47d797de9f891d4d8acb047a24ca37a60294dd/'
    'pip-26.2.1-py3-none-any.whl"\n'
    'PIP_BOOTSTRAP_SHA256="71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e"\n',
    "bootstrap constants",
)
install = replace_once(
    install,
    '  Create a Python virtual environment when supported and install requirements\n',
    '  Create an isolated Python virtual environment and install requirements\n'
    '  Use a pinned, hash-verified pip bootstrap wheel inside the venv when ensurepip is unavailable\n',
    "dry-run runtime plan",
)

old_runtime = '''echo "Preparing Python runtime..."
if python3 -m venv "$INSTALL_DIR/.venv" >/tmp/truepanel-venv.log 2>&1; then
  PYTHON_BIN="$INSTALL_DIR/.venv/bin/python"

  echo "Installing Python dependencies into virtual environment..."
  "$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
  "$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
else
  echo "Virtual environment unavailable."
  echo "Using system Python instead."
  echo
  echo "Reason:"
  cat /tmp/truepanel-venv.log
  echo

  PYTHON_BIN="$(command -v python3)"
fi

echo "Checking Python imports..."
"$PYTHON_BIN" - <<'PY'
missing = []

for module in ["yaml"]:
    try:
        __import__(module)
    except Exception:
        missing.append(module)

if missing:
    print("Missing Python modules: " + ", ".join(missing))
    print("Install dependencies or run TruePanel from an environment that provides them.")
    raise SystemExit(1)

print("Python imports OK")
PY
'''

new_runtime = '''echo "Preparing Python runtime..."
VENV_DIR="$INSTALL_DIR/.venv"
VENV_LOG="/tmp/truepanel-venv.log"
PIP_BOOTSTRAP_WHEEL="/tmp/truepanel-pip-$PIP_BOOTSTRAP_VERSION.whl"
PIP_RUNNER=()

if python3 -m ensurepip --version >/tmp/truepanel-ensurepip.log 2>&1
then
  echo "Creating isolated virtual environment with ensurepip..."
  if ! python3 -m venv "$VENV_DIR" >"$VENV_LOG" 2>&1
  then
    echo "Could not create the isolated TruePanel Python runtime." >&2
    cat "$VENV_LOG" >&2
    exit 1
  fi

  PYTHON_BIN="$VENV_DIR/bin/python"
  PIP_RUNNER=("$PYTHON_BIN" -m pip)
else
  echo "ensurepip is unavailable; creating an isolated pipless virtual environment..."
  if ! python3 -m venv --without-pip "$VENV_DIR" >"$VENV_LOG" 2>&1
  then
    echo "Could not create the isolated TruePanel Python runtime." >&2
    cat "$VENV_LOG" >&2
    exit 1
  fi

  PYTHON_BIN="$VENV_DIR/bin/python"

  echo "Downloading pinned pip bootstrap wheel..."
  "$PYTHON_BIN" - \
    "$PIP_BOOTSTRAP_URL" \
    "$PIP_BOOTSTRAP_SHA256" \
    "$PIP_BOOTSTRAP_WHEEL" <<'PYPIP'
from pathlib import Path
import hashlib
import sys
import urllib.request

url, expected_sha256, destination = sys.argv[1:]

try:
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = response.read()
except Exception as exc:
    print(
        f"Could not download pinned pip bootstrap wheel: {exc}",
        file=sys.stderr,
    )
    raise SystemExit(1)

actual_sha256 = hashlib.sha256(payload).hexdigest()
if actual_sha256 != expected_sha256:
    print(
        "Pinned pip bootstrap wheel failed SHA256 verification: "
        f"expected {expected_sha256}, got {actual_sha256}",
        file=sys.stderr,
    )
    raise SystemExit(1)

Path(destination).write_bytes(payload)
print(f"Pinned pip bootstrap wheel verified: {actual_sha256}")
PYPIP

  if ! PYTHONPATH="$PIP_BOOTSTRAP_WHEEL" \
    "$PYTHON_BIN" -m pip --version >/dev/null
  then
    echo "Pinned pip bootstrap wheel could not run inside the isolated venv." >&2
    exit 1
  fi

  PIP_RUNNER=(env "PYTHONPATH=$PIP_BOOTSTRAP_WHEEL" "$PYTHON_BIN" -m pip)
fi

echo "Installing Python dependencies into isolated virtual environment..."
"${PIP_RUNNER[@]}" install -r "$INSTALL_DIR/requirements.txt"

echo "Checking Python runtime imports..."
"$PYTHON_BIN" - <<'PY'
required = {
    "serial": "pyserial",
    "psutil": "psutil",
    "yaml": "PyYAML",
}
missing = []

for module, package in required.items():
    try:
        __import__(module)
    except Exception as exc:
        missing.append(f"{package} ({module}: {exc})")

if missing:
    print("Missing Python runtime dependencies: " + ", ".join(missing))
    raise SystemExit(1)

print("Python runtime imports OK")
PY
'''

install = replace_once(install, old_runtime, new_runtime, "python runtime block")
INSTALL.write_text(install, encoding="utf-8")


tests = TESTS.read_text(encoding="utf-8")
if "test_install_bootstraps_pipless_venv" in tests:
    raise SystemExit("tests already patched")
tests = tests.rstrip() + '''


def test_install_bootstraps_pipless_venv_without_system_runtime_fallback():
    text = source("install.sh")

    assert 'PIP_BOOTSTRAP_VERSION="26.2.1"' in text
    assert (
        'PIP_BOOTSTRAP_SHA256="'
        '71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e"'
        in text
    )
    assert "python3 -m venv --without-pip" in text
    assert "urllib.request.urlopen(url, timeout=60)" in text
    assert "hashlib.sha256(payload).hexdigest()" in text
    assert 'PYTHONPATH="$PIP_BOOTSTRAP_WHEEL"' in text
    assert 'PIP_RUNNER=(env "PYTHONPATH=$PIP_BOOTSTRAP_WHEEL"' in text
    assert "Using system Python instead." not in text
    assert 'PYTHON_BIN="$(command -v python3)"' not in text


def test_install_checks_all_runtime_dependencies_before_service_writes():
    text = source("install.sh")

    check = text.index("required = {")
    cli_write = text.index('echo "Creating CLI directory..."')
    mission_write = text.index(
        'cat > "$MISSION_CONTROL_SERVICE_FILE"'
    )
    runtime_check = text[check:cli_write]

    assert '"serial": "pyserial"' in runtime_check
    assert '"psutil": "psutil"' in runtime_check
    assert '"yaml": "PyYAML"' in runtime_check
    assert check < cli_write < mission_write


def test_install_docs_keep_dependencies_out_of_system_python():
    text = source("docs/INSTALLATION.md")

    assert "pinned, hash-verified pip wheel" in text
    assert "does not install TruePanel dependencies into system Python" in text
''' + "\n"
TESTS.write_text(tests, encoding="utf-8")


docs = DOCS.read_text(encoding="utf-8")
docs = replace_once(
    docs,
    '- Access to the relevant serial, SMBus, and sysfs hardware paths\n',
    '- Access to the relevant serial, SMBus, and sysfs hardware paths\n'
    '- Network access to PyPI while the installer prepares the isolated Python runtime\n',
    "requirements docs",
)
docs = replace_once(
    docs,
    '''1. copies the repository to `/mnt/POOL/DATASET/TruePanel`;
2. attempts to create a Python virtual environment;
3. falls back to system Python when the TrueNAS Python environment cannot create a usable venv;
4. verifies required imports;
5. creates the CLI wrapper;
6. creates the primary LCD and Mission Control service units;
7. creates the dormant standalone Host Agent unit with its cutover-marker condition and no `[Install]` section;
8. leaves all services stopped so activation remains an explicit operator action;
9. runs `truepanel doctor`.
''',
    '''1. copies the repository to `/mnt/POOL/DATASET/TruePanel`;
2. creates an isolated Python virtual environment;
3. when TrueNAS lacks `ensurepip`, creates the venv with `--without-pip`, downloads a pinned, hash-verified pip wheel from PyPI, and runs pip from that wheel inside the venv;
4. installs `requirements.txt` inside the isolated venv and verifies `pyserial`, `psutil`, and `PyYAML`;
5. does not install TruePanel dependencies into system Python;
6. creates the CLI wrapper;
7. creates the primary LCD and Mission Control service units;
8. creates the dormant standalone Host Agent unit with its cutover-marker condition and no `[Install]` section;
9. leaves all services stopped so activation remains an explicit operator action;
10. runs `truepanel doctor`.
''',
    "installer docs",
)
DOCS.write_text(docs, encoding="utf-8")
