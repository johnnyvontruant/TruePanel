#!/usr/bin/env bash
set -e

INSTALL_DIR="/opt/truepanel"
SERVICE_FILE="/etc/systemd/system/truepanel.service"

echo "== TruePanel Installer =="

echo "Stopping existing service if present..."
systemctl stop truepanel 2>/dev/null || true

echo "Creating clean install directory..."
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

echo "Copying files..."
rsync -a \
  --exclude ".git" \
  --exclude ".venv" \
  --exclude "__pycache__" \
  --exclude ".ruff_cache" \
  --exclude "development/backups" \
  ./ "$INSTALL_DIR/"

echo "Creating Python virtual environment..."
if python3 -m venv "$INSTALL_DIR/.venv" >/tmp/truepanel-venv.log 2>&1; then
    PYTHON="$INSTALL_DIR/.venv/bin/python"

    if [ -x "$INSTALL_DIR/.venv/bin/pip" ] && [ -f "$INSTALL_DIR/requirements.txt" ]; then
        echo "Installing Python dependencies..."
        "$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
        "$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
    else
        echo "pip unavailable; continuing without dependency install."
    fi
else
    echo "Standard venv failed; trying TrueNAS-safe venv without pip..."
    python3 -m venv --without-pip "$INSTALL_DIR/.venv"
    PYTHON="$INSTALL_DIR/.venv/bin/python"
fi

echo "Creating systemd service..."
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=TruePanel QNAP LCD Front Panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$PYTHON $INSTALL_DIR/truepanel.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "Reloading systemd..."
systemctl daemon-reload
systemctl enable truepanel

echo
echo "Install complete."
echo
echo "Start with:"
echo "  systemctl start truepanel"
echo
echo "View logs with:"
echo "  journalctl -u truepanel -f"
