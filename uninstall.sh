#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_CLI="$SCRIPT_DIR/truepanel.py"

INSTALL_DIR="${TRUEPANEL_INSTALL_ROOT:-}"
DRY_RUN=0
SERVICE_NAME="truepanel.service"
MISSION_SERVICE_NAME="truepanel-mission-control.service"
HOST_AGENT_SERVICE_NAME="truepanel-host-agent.service"
SERVICE_FILE="/etc/systemd/system/truepanel.service"
MISSION_SERVICE_FILE="/etc/systemd/system/truepanel-mission-control.service"
HOST_AGENT_SERVICE_FILE="/etc/systemd/system/truepanel-host-agent.service"
MISSION_ENV_FILE="/etc/default/truepanel-mission-control"
LEGACY_BIN_FILE="/usr/local/bin/truepanel"
RUNTIME_DIR="/run/truepanel"
CUTOVER_MARKER_FILE="/run/truepanel/standalone-host-agent.enabled"
HOST_OWNERSHIP_FILE="/run/truepanel/host-owner.lock"
FAN_SOCKET_FILE="/run/truepanel/fan-control.sock"
FAN_STATUS_FILE="/run/truepanel/fan-control-status.json"
LCD_COMMAND_SOCKET_FILE="/run/truepanel/lcd-command.sock"
LCD_READER_STATUS_FILE="/run/truepanel/lcd-reader-status.json"
LCD_DISPLAY_STATUS_FILE="/run/truepanel/lcd-display-status.json"

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

print_uninstall_plan() {
  cat <<EOF
== TruePanel Uninstall Dry Run ==

Install root:
  $INSTALL_DIR

Services that would be stopped and verified inactive:
  $HOST_AGENT_SERVICE_NAME
  $SERVICE_NAME
  $MISSION_SERVICE_NAME

Safety gates required before destructive cleanup:
  Host ownership lease must be released: $HOST_OWNERSHIP_FILE
  Motherboard fan control must verify Automatic using: $CONFIG_FILE

Service scaffolding that would be removed:
  $SERVICE_FILE
  $MISSION_SERVICE_FILE
  $HOST_AGENT_SERVICE_FILE
  $MISSION_ENV_FILE

Runtime state that would be removed:
  $CUTOVER_MARKER_FILE
  $FAN_SOCKET_FILE
  $FAN_STATUS_FILE
  $LCD_COMMAND_SOCKET_FILE
  $LCD_READER_STATUS_FILE
  $LCD_DISPLAY_STATUS_FILE
  $HOST_OWNERSHIP_FILE
  $RUNTIME_DIR (when empty)

CLI/install paths that would be removed:
  $BIN_FILE
  $LEGACY_BIN_FILE
  $INSTALL_DIR

Systemd daemon state would be reloaded after service-file removal.

DRY RUN ONLY: no services were stopped, no fan state changed, no files were removed.
EOF
}

stop_service() {
  local service="$1"
  local state=""

  printf 'Stopping %s...\n' "$service"
  systemctl stop "$service" 2>/dev/null || true

  state="$(
    systemctl is-active "$service" 2>/dev/null || true
  )"

  case "$state" in
    active|activating|deactivating|reloading)
      printf 'Refusing to uninstall while %s is still active.\n' \
        "$service" >&2
      exit 1
      ;;
  esac
}

assert_host_ownership_released() {
  if [[ ! -e "$HOST_OWNERSHIP_FILE" ]]
  then
    return 0
  fi

  if ! python3 - "$HOST_OWNERSHIP_FILE" <<'PY'
import fcntl
import sys

path = sys.argv[1]

with open(path, "a+", encoding="utf-8") as handle:
    try:
        fcntl.flock(
            handle.fileno(),
            fcntl.LOCK_EX | fcntl.LOCK_NB,
        )
    except BlockingIOError:
        raise SystemExit(1)
PY
  then
    printf '%s\n' \
      'Host hardware ownership is still held; refusing runtime cleanup.' \
      >&2
    exit 1
  fi
}

verify_fan_safety() {
  if [[ ! -f "$CONFIG_FILE" ]]
  then
    printf 'TruePanel configuration is unavailable: %s\n' \
      "$CONFIG_FILE" >&2
    printf '%s\n' \
      'Refusing uninstall because fan restoration cannot be verified.' \
      >&2
    exit 1
  fi

  local verifier=()

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
  then
    printf '%s\n' \
      'Motherboard Automatic fan control was not confirmed.' \
      'Refusing destructive uninstall cleanup; installation remains in place.' \
      >&2
    exit 1
  fi
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
    systemctl show truepanel.service \
      --property=WorkingDirectory \
      --value \
      --no-pager \
      2>/dev/null \
      || true
  )"
fi

if [[ -z "$INSTALL_DIR" ]]
then
  printf '%s\n' \
    'Could not determine the TruePanel installation root.' \
    'Use --root /mnt/POOL/DATASET/TruePanel.' \
    >&2
  exit 1
fi

if ! INSTALL_DIR="$(normalize_install_root "$INSTALL_DIR")"
then
  exit 1
fi

BIN_FILE="$INSTALL_DIR/bin/truepanel"
VENV_PYTHON="$INSTALL_DIR/.venv/bin/python"
CONFIG_FILE="$INSTALL_DIR/truepanel.yaml"

if [[ "$DRY_RUN" -eq 1 ]]
then
  print_uninstall_plan
  exit 0
fi

if [[ $EUID -ne 0 ]]
then
  echo "Please run as root: sudo ./uninstall.sh"
  exit 1
fi

echo "== TruePanel Uninstaller =="

# Stop every process that can own or consume TruePanel runtime state before
# deleting sockets, status files, the cutover marker, or the ownership lock.
stop_service "$HOST_AGENT_SERVICE_NAME"
stop_service "$SERVICE_NAME"
stop_service "$MISSION_SERVICE_NAME"

# A manually launched Host Agent may exist outside systemd. Refuse cleanup if
# any process still owns the cross-process hardware lease.
assert_host_ownership_released

# Host shutdown requests motherboard Automatic restoration. Prove the
# configured channels actually returned to Automatic before deleting the
# installed runtime needed for diagnosis or recovery.
verify_fan_safety

echo "Disabling installed services..."
systemctl disable "$SERVICE_NAME" 2>/dev/null || true
systemctl disable "$MISSION_SERVICE_NAME" 2>/dev/null || true
systemctl disable "$HOST_AGENT_SERVICE_NAME" 2>/dev/null || true

echo "Removing service files..."
rm -f "$SERVICE_FILE" "$MISSION_SERVICE_FILE" "$HOST_AGENT_SERVICE_FILE"
rm -f "$MISSION_ENV_FILE"

echo "Removing runtime state..."
rm -f \
  "$CUTOVER_MARKER_FILE" \
  "$FAN_SOCKET_FILE" \
  "$FAN_STATUS_FILE" \
  "$LCD_COMMAND_SOCKET_FILE" \
  "$LCD_READER_STATUS_FILE" \
  "$LCD_DISPLAY_STATUS_FILE" \
  "$HOST_OWNERSHIP_FILE"
rmdir "$RUNTIME_DIR" 2>/dev/null || true

echo "Removing CLI wrapper..."
rm -f "$BIN_FILE" "$LEGACY_BIN_FILE"

echo "Reloading systemd..."
systemctl daemon-reload

echo "Removing install directory..."
rm -rf "$INSTALL_DIR"

echo
echo "TruePanel has been uninstalled."
