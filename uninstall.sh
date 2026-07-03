#!/usr/bin/env bash
set -euo pipefail

APP_NAME="truepanel"
INSTALL_DIR="/opt/truepanel"
SERVICE_FILE="/etc/systemd/system/truepanel.service"
BIN_FILE="/usr/local/bin/truepanel"

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
rm -f "$BIN_FILE"

echo "Reloading systemd..."
systemctl daemon-reload

echo "Removing install directory..."
rm -rf "$INSTALL_DIR"

echo
echo "TruePanel has been uninstalled."
