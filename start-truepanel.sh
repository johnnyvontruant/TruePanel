#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
  pwd
)"

SYSTEMD_DIR="${TRUEPANEL_SYSTEMD_DIR:-/etc/systemd/system}"
ENV_DIR="${TRUEPANEL_ENV_DIR:-/etc/default}"
SYSTEMCTL_BIN="${TRUEPANEL_SYSTEMCTL_BIN:-systemctl}"
SKIP_SYSTEMCTL="${TRUEPANEL_SKIP_SYSTEMCTL:-false}"

LCD_SERVICE_FILE="$SYSTEMD_DIR/truepanel.service"
HOST_AGENT_SERVICE_FILE="$SYSTEMD_DIR/truepanel-host-agent.service"
MISSION_SERVICE_FILE="$SYSTEMD_DIR/truepanel-mission-control.service"
MISSION_ENV_FILE="$ENV_DIR/truepanel-mission-control"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]
then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
  PYTHON_BIN="$(
    command -v python3
  )"
fi

if [[ -z "${PYTHON_BIN:-}" ]]
then
  printf 'TruePanel startup failed: Python is unavailable.\n' >&2
  exit 1
fi

if [[ ! -f "$ROOT_DIR/truepanel.py" ]]
then
  printf 'TruePanel startup failed: missing %s\n' \
    "$ROOT_DIR/truepanel.py" >&2
  exit 1
fi

if [[ ! -f "$ROOT_DIR/truepanel.yaml" ]]
then
  printf 'TruePanel startup failed: missing %s\n' \
    "$ROOT_DIR/truepanel.yaml" >&2
  exit 1
fi

install -d -m 0755 \
  "$SYSTEMD_DIR" \
  "$ENV_DIR"

if [[ ! -f "$MISSION_ENV_FILE" ]]
then
  cat > "$MISSION_ENV_FILE" <<ENV
TRUEPANEL_MC_HOST=0.0.0.0
TRUEPANEL_MC_PORT=8787
TRUEPANEL_MC_CONFIG_PATH=$ROOT_DIR/truepanel.yaml
TRUEPANEL_MC_ALLOW_CONFIG_WRITES=false
ENV

  chmod 0644 "$MISSION_ENV_FILE"

  printf 'Created Mission Control environment: %s\n' \
    "$MISSION_ENV_FILE"
else
  printf 'Preserved Mission Control environment: %s\n' \
    "$MISSION_ENV_FILE"
fi

cat > "$LCD_SERVICE_FILE" <<SERVICE
[Unit]
Description=TruePanel QNAP LCD Front Panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT_DIR
ExecStart=$PYTHON_BIN $ROOT_DIR/truepanel.py run
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

cat > "$HOST_AGENT_SERVICE_FILE" <<SERVICE
[Unit]
Description=TruePanel Privileged Host Agent (standalone activation locked)
After=local-fs.target
ConditionPathExists=/run/truepanel/standalone-host-agent.enabled

[Service]
Type=simple
WorkingDirectory=$ROOT_DIR
ExecStart=$PYTHON_BIN -m truepanel.host.agent
Restart=on-failure
RestartSec=5
TimeoutStopSec=15
UMask=0027
SERVICE

cat > "$MISSION_SERVICE_FILE" <<SERVICE
[Unit]
Description=TruePanel Mission Control Web Dashboard
After=network-online.target truepanel.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT_DIR
EnvironmentFile=-$MISSION_ENV_FILE
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
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
UMask=0027

[Install]
WantedBy=multi-user.target
SERVICE

chmod 0644 \
  "$LCD_SERVICE_FILE" \
  "$HOST_AGENT_SERVICE_FILE" \
  "$MISSION_SERVICE_FILE"

printf 'Installed service unit: %s\n' \
  "$LCD_SERVICE_FILE"
printf 'Installed dormant service unit: %s\n' \
  "$HOST_AGENT_SERVICE_FILE"
printf 'Installed service unit: %s\n' \
  "$MISSION_SERVICE_FILE"
printf '%s\n' \
  'Standalone Host Agent activation remains locked; unit was not enabled or started.'

if [[ "$SKIP_SYSTEMCTL" == "true" ]]
then
  printf 'Systemctl actions skipped by request.\n'
  exit 0
fi

"$SYSTEMCTL_BIN" daemon-reload

"$SYSTEMCTL_BIN" enable \
  truepanel.service \
  truepanel-mission-control.service

"$SYSTEMCTL_BIN" restart \
  truepanel.service \
  truepanel-mission-control.service

printf 'TruePanel services restored and started.\n'
