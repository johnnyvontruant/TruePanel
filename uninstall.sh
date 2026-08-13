#!/usr/bin/env bash

set -euo pipefail

INSTALL_DIR="${TRUEPANEL_INSTALL_ROOT:-}"
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
  printf 'Usage: %s --root /mnt/POOL/DATASET/TruePanel\n' "$0"
  printf '       TRUEPANEL_INSTALL_ROOT=/mnt/POOL/DATASET/TruePanel %s\n' "$0"
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

if [[ $EUID -ne 0 ]]
then
  echo "Please run as root: sudo ./uninstall.sh"
  exit 1
fi

if [[ -z "$INSTALL_DIR" ]]
then
  INSTALL_DIR="$(
    systemctl show "$SERVICE_NAME" \
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

case "$INSTALL_DIR" in
  /mnt/*)
    ;;
  *)
    printf 'Installation root must be under /mnt/: %s\n' \
      "$INSTALL_DIR" >&2
    exit 1
    ;;
esac

BIN_FILE="$INSTALL_DIR/bin/truepanel"

echo "== TruePanel Uninstaller =="

# Stop every process that can own or consume TruePanel runtime state before
# deleting sockets, status files, the cutover marker, or the ownership lock.
stop_service "$HOST_AGENT_SERVICE_NAME"
stop_service "$SERVICE_NAME"
stop_service "$MISSION_SERVICE_NAME"

# A manually launched Host Agent may exist outside systemd. Refuse cleanup if
# any process still owns the cross-process hardware lease.
assert_host_ownership_released

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
