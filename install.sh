#!/usr/bin/env bash

set -euo pipefail

SOURCE_ROOT="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
  pwd
)"

INSTALL_DIR="${TRUEPANEL_INSTALL_ROOT:-}"
DRY_RUN=0
SERVICE_FILE="/etc/systemd/system/truepanel.service"
HOST_AGENT_SERVICE_FILE="/etc/systemd/system/truepanel-host-agent.service"
MISSION_CONTROL_SERVICE_FILE="/etc/systemd/system/truepanel-mission-control.service"
MISSION_CONTROL_ENV_FILE="/etc/default/truepanel-mission-control"
PYTHON_BIN=""
PIP_BOOTSTRAP_VERSION="26.2.1"
PIP_BOOTSTRAP_URL="https://files.pythonhosted.org/packages/f3/6e/1736e5b4ae2b778ef2f81c47d797de9f891d4d8acb047a24ca37a60294dd/pip-26.2.1-py3-none-any.whl"
PIP_BOOTSTRAP_SHA256="71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e"

usage() {
  printf 'Usage: %s [--dry-run] --root /mnt/POOL/DATASET/TruePanel\n' "$0"
  printf '       TRUEPANEL_INSTALL_ROOT=/mnt/POOL/DATASET/TruePanel %s [--dry-run]\n' "$0"
}


normalize_install_root() {
  python3 - "$1" <<'PYROOT'
from pathlib import Path
import sys

raw = sys.argv[1]
resolved = Path(raw).expanduser().resolve(strict=False)
parts = resolved.parts

# Require at least /mnt/<pool>/<managed-directory>. Never permit a pool
# mount itself, /mnt, or a textual /mnt path that resolves elsewhere.
if (
    len(parts) < 4
    or parts[0] != "/"
    or parts[1] != "mnt"
):
    print(
        "Installation root must resolve below "
        "/mnt/<pool>/ and may not be the pool root: "
        f"{resolved}",
        file=sys.stderr,
    )
    raise SystemExit(1)

print(resolved)
PYROOT
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
  Create/preserve install root and synchronize only managed source files
  Exclude source-local config, secrets, virtualenvs, caches, history, and plugin state
  Preserve an existing target truepanel.yaml; create the safe default only when target config is absent
  Create an isolated Python virtual environment and install requirements
  Use a pinned, hash-verified pip bootstrap wheel inside the venv when ensurepip is unavailable
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

while [[ $# -gt 0 ]]
do
  case "$1" in
    --root)
      if [[ -z "${2:-}" ]]
      then
        printf 'Missing value for --root.\n' >&2
        usage >&2
        exit 2
      fi

      INSTALL_DIR="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$INSTALL_DIR" ]]
then
  INSTALL_DIR="$(
    systemctl show truepanel.service       --property=WorkingDirectory       --value       --no-pager       2>/dev/null       || true
  )"
fi

if [[ -z "$INSTALL_DIR" ]]
then
  printf '%s\n'     'No persistent TruePanel installation root was provided.'     'Use --root /mnt/POOL/DATASET/TruePanel.'     'The installer will not guess a storage pool or use the system root filesystem.'     >&2
  exit 1
fi

if ! INSTALL_DIR="$(normalize_install_root "$INSTALL_DIR")"
then
  exit 1
fi

if [[ "$DRY_RUN" -eq 1 ]]
then
  print_install_plan
  exit 0
fi

if [[ "$(id -u)" -ne 0 ]]
then
  printf 'Please run as root: sudo %s --root %s\n' \
    "$0" "$INSTALL_DIR" >&2
  exit 1
fi

mkdir -p -- "$INSTALL_DIR"

INSTALL_DIR="$(
  cd -- "$INSTALL_DIR"
  pwd
)"

BIN_DIR="$INSTALL_DIR/bin"
BIN_FILE="$BIN_DIR/truepanel"

echo "== TruePanel Installer =="
echo
echo "Installation root:"
echo "  $INSTALL_DIR"
echo

echo "Checking prerequisites..."
for command in python3 rsync systemctl; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing required command: $command"
    exit 1
  fi
done

echo "Creating install directory..."
mkdir -p "$INSTALL_DIR"

echo "Copying files..."
rsync -a --delete \
  --exclude ".git" \
  --exclude ".env" \
  --exclude ".venv" \
  --exclude "venv" \
  --exclude ".quality-venv" \
  --exclude ".pytest_cache" \
  --exclude ".ruff_cache" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  --exclude "*.egg-info" \
  --exclude "truepanel.yaml" \
  --exclude "truepanel.backup-*" \
  --exclude "var/history" \
  --exclude "development/logs" \
  --exclude "development/backups" \
  --exclude "plugins/.truepanel-plugin-state.json" \
  "$SOURCE_ROOT/" "$INSTALL_DIR/"

echo "Creating default configuration if needed..."
if [ ! -f "$INSTALL_DIR/truepanel.yaml" ]; then
  cat > "$INSTALL_DIR/truepanel.yaml" <<'YAML'
theme_pack: default

flightdeck:
  rotation_interval: 5
  pause_after_button: 60
  idle_slowdown_after: 3600
  idle_interval: 30

  transitions:
    enabled: true

  startup:
    enabled: true
    delay: 0.75
    diagnostics: true

  night_mode:
    enabled: true
    idle_after: 1800
    rotation_interval: 60
    suppress_info: true
    dashboard_pages:
      - home
      - storage

theme:
  healthy_message: "Mission Ready"
  startup_title: "TruePanel"
  startup_subtitle: "Flight Deck"
  warning_prefix: "! "
  critical_prefix: "!!"
  info_prefix: "i "
  healthy_prefix: "OK"

buzzer:
  enabled: false
  backend: pcspkr
YAML
fi

echo "Preparing Python runtime..."
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
  "$PYTHON_BIN" -     "$PIP_BOOTSTRAP_URL"     "$PIP_BOOTSTRAP_SHA256"     "$PIP_BOOTSTRAP_WHEEL" <<'PYPIP'
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

  if ! PYTHONPATH="$PIP_BOOTSTRAP_WHEEL"     "$PYTHON_BIN" -m pip --version >/dev/null
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

echo "Creating CLI directory..."
mkdir -p "$BIN_DIR"

echo "Creating CLI wrapper..."
cat > "$BIN_FILE" <<CLI
#!/usr/bin/env bash
cd "$INSTALL_DIR"
exec "$PYTHON_BIN" "$INSTALL_DIR/truepanel.py" "\$@"
CLI

chmod +x "$BIN_FILE"

echo "Installing Mission Control service..."
cat > "$MISSION_CONTROL_SERVICE_FILE" <<SERVICE
[Unit]
Description=TruePanel Mission Control Web Dashboard
After=network-online.target truepanel.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=-$MISSION_CONTROL_ENV_FILE
ExecStart=$PYTHON_BIN -m truepanel.web.service
Restart=on-failure
RestartSec=5
TimeoutStopSec=15
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK
UMask=0027

[Install]
WantedBy=multi-user.target
SERVICE

chmod 0644 "$MISSION_CONTROL_SERVICE_FILE"

echo "Creating Mission Control environment if needed..."
if [ ! -f "$MISSION_CONTROL_ENV_FILE" ]; then
  cat > "$MISSION_CONTROL_ENV_FILE" <<ENV
TRUEPANEL_MC_HOST=127.0.0.1
TRUEPANEL_MC_PORT=8787
TRUEPANEL_MC_CONFIG_PATH=$INSTALL_DIR/truepanel.yaml
TRUEPANEL_MC_ALLOW_CONFIG_WRITES=false
ENV

  chmod 0644 "$MISSION_CONTROL_ENV_FILE"
else
  echo "Preserving existing Mission Control environment:"
  echo "  $MISSION_CONTROL_ENV_FILE"
fi

echo "Installing dormant Host Agent service..."
cat > "$HOST_AGENT_SERVICE_FILE" <<SERVICE
[Unit]
Description=TruePanel Privileged Host Agent (standalone activation locked)
After=local-fs.target
ConditionPathExists=/run/truepanel/standalone-host-agent.enabled

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$PYTHON_BIN -m truepanel.host.agent
Restart=on-failure
RestartSec=5
TimeoutStopSec=15
UMask=0027
SERVICE

chmod 0644 "$HOST_AGENT_SERVICE_FILE"
echo "Standalone Host Agent activation remains locked; unit was not enabled or started."

echo "Creating systemd service..."
cat > "$SERVICE_FILE" <<SERVICE
[Unit]
Description=TruePanel QNAP LCD Front Panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$BIN_FILE run
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

echo "Reloading systemd..."
systemctl daemon-reload

echo
echo "Running TruePanel Doctor..."
if "$BIN_FILE" doctor; then
  DOCTOR_STATUS="MISSION READY"
else
  DOCTOR_STATUS="MISSION DEGRADED"
fi

echo
echo "TruePanel Install Complete"
echo "=========================="
echo
echo "$DOCTOR_STATUS"
echo
echo "Try:"
echo "  $BIN_FILE doctor"
echo "  $BIN_FILE plugins"
echo "  $BIN_FILE simulate thermal --steps 5 --delay 0.2"
echo
echo "Start with:"
echo "  systemctl start truepanel"
echo
echo "Enable on boot with:"
echo "  systemctl enable truepanel"
echo
echo "View logs with:"
echo "  journalctl -u truepanel -f"
echo
echo "Mission Control is installed but remains disabled by default."
echo
echo "Configure Mission Control with:"
echo "  $MISSION_CONTROL_ENV_FILE"
echo
echo "Start Mission Control with:"
echo "  systemctl start truepanel-mission-control"
echo
echo "Enable Mission Control on boot with:"
echo "  systemctl enable truepanel-mission-control"
echo
echo "View Mission Control logs with:"
echo "  journalctl -u truepanel-mission-control -f"
echo
echo "Default Mission Control address:"
echo "  http://127.0.0.1:8787"
echo
echo "LAN access requires setting TRUEPANEL_MC_HOST=0.0.0.0"
echo "Configuration writes require setting TRUEPANEL_MC_ALLOW_CONFIG_WRITES=true"
