#!/usr/bin/env bash
set -euo pipefail

APP_NAME="truepanel"
INSTALL_DIR="/opt/truepanel"
SERVICE_FILE="/etc/systemd/system/truepanel.service"
BIN_FILE="/usr/local/bin/truepanel"

echo "== TruePanel Installer =="

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo ./install.sh"
  exit 1
fi

echo "Creating install directory..."
mkdir -p "$INSTALL_DIR"

echo "Copying files..."
rsync -a --delete \
  --exclude ".git" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  ./ "$INSTALL_DIR/"

echo "Creating Python virtual environment..."
python3 -m venv "$INSTALL_DIR/.venv"

echo "Installing Python dependencies..."
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

echo "Creating CLI wrapper..."
cat > "$BIN_FILE" <<CLI
#!/usr/bin/env bash
cd "$INSTALL_DIR"
exec "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/truepanel.py" "\$@"
CLI

chmod +x "$BIN_FILE"

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
echo "Install complete."
echo
echo "Try:"
echo "  truepanel doctor"
echo "  truepanel plugins"
echo "  truepanel simulate thermal --steps 5 --delay 0.2"
echo
echo "Start with:"
echo "  systemctl start truepanel"
echo
echo "Enable on boot with:"
echo "  systemctl enable truepanel"
echo
echo "View logs with:"
echo "  journalctl -u truepanel -f"
