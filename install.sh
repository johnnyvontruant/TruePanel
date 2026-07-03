#!/usr/bin/env bash
set -euo pipefail

APP_NAME="truepanel"
INSTALL_DIR="/opt/truepanel"
SERVICE_FILE="/etc/systemd/system/truepanel.service"
BIN_FILE="/usr/local/bin/truepanel"

echo "== TruePanel Installer =="
echo

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo ./install.sh"
  exit 1
fi

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
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  ./ "$INSTALL_DIR/"

echo "Creating default configuration if needed..."
if [[ ! -f "$INSTALL_DIR/truepanel.yaml" ]]; then
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
YAML
fi

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
