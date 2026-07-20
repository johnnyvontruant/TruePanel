INSTALL_DIR="/opt/truepanel"
SERVICE_FILE="/etc/systemd/system/truepanel.service"
MISSION_CONTROL_SERVICE_FILE="/etc/systemd/system/truepanel-mission-control.service"
MISSION_CONTROL_ENV_FILE="/etc/default/truepanel-mission-control"
BIN_DIR="$INSTALL_DIR/bin"
BIN_FILE="$BIN_DIR/truepanel"
PYTHON_BIN=""

echo "== TruePanel Installer =="
echo

if [ "$(id -u)" -ne 0 ]; then
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
YAML
fi

echo "Preparing Python runtime..."
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
install -m 0644   "$INSTALL_DIR/packaging/systemd/truepanel-mission-control.service"   "$MISSION_CONTROL_SERVICE_FILE"

echo "Creating Mission Control environment if needed..."
if [ ! -f "$MISSION_CONTROL_ENV_FILE" ]; then
  install -m 0644     "$INSTALL_DIR/packaging/systemd/truepanel-mission-control.env"     "$MISSION_CONTROL_ENV_FILE"
else
  echo "Preserving existing Mission Control environment:"
  echo "  $MISSION_CONTROL_ENV_FILE"
fi

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
