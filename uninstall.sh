#!/usr/bin/env bash

set -euo pipefail

APP_NAME="truepanel"
INSTALL_DIR="${TRUEPANEL_INSTALL_ROOT:-}"
SERVICE_FILE="/etc/systemd/system/truepanel.service"
MISSION_SERVICE_FILE="/etc/systemd/system/truepanel-mission-control.service"
MISSION_ENV_FILE="/etc/default/truepanel-mission-control"
LEGACY_BIN_FILE="/usr/local/bin/truepanel"

usage() {
  printf 'Usage: %s --root /mnt/POOL/DATASET/TruePanel\n' "$0"
  printf '       TRUEPANEL_INSTALL_ROOT=/mnt/POOL/DATASET/TruePanel %s\n' "$0"
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

if [[ -z "$INSTALL_DIR" ]]
then
  INSTALL_DIR="$(
    systemctl show truepanel.service       --property=WorkingDirectory       --value       --no-pager       2>/dev/null       || true
  )"
fi

if [[ -z "$INSTALL_DIR" ]]
then
  printf '%s\n'     'Could not determine the TruePanel installation root.'     'Use --root /mnt/POOL/DATASET/TruePanel.'     >&2
  exit 1
fi

case "$INSTALL_DIR" in
  /mnt/*)
    ;;
  *)
    printf 'Installation root must be under /mnt/: %s\n'       "$INSTALL_DIR" >&2
    exit 1
    ;;
esac

BIN_FILE="$INSTALL_DIR/bin/truepanel"

echo "== TruePanel Uninstaller =="

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo ./uninstall.sh"
  exit 1
fi

echo "Stopping service..."
systemctl stop "$APP_NAME" 2>/dev/null || true

echo "Disabling service..."
systemctl disable "$APP_NAME" 2>/dev/null || true

echo "Removing service file..."
rm -f "$SERVICE_FILE"

echo "Removing CLI wrapper..."
rm -f "$BIN_FILE" "$LEGACY_BIN_FILE"

echo "Reloading systemd..."
systemctl daemon-reload

echo "Removing install directory..."
rm -rf "$INSTALL_DIR"

echo
echo "TruePanel has been uninstalled."
