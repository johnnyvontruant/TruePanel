#!/usr/bin/env bash

set -euo pipefail

SOURCE_ROOT="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
  pwd
)"

DEPLOYED_ROOT="${TRUEPANEL_DEPLOY_ROOT:-}"

if [[ -z "$DEPLOYED_ROOT" ]]
then
  DEPLOYED_ROOT="$(
    systemctl show truepanel.service \
      --property=WorkingDirectory \
      --value \
      --no-pager \
      2>/dev/null \
      || true
  )"
fi

if [[ -z "$DEPLOYED_ROOT" ]]
then
  printf '%s\n' \
    'Could not determine the deployed TruePanel root.' \
    'Set TRUEPANEL_DEPLOY_ROOT to the persistent installation path.' \
    >&2
  exit 1
fi

DEPLOYED_ROOT="$(
  cd -- "$DEPLOYED_ROOT" 2>/dev/null
  pwd
)" || {
  printf 'Deployment root does not exist: %s\n' \
    "$DEPLOYED_ROOT" >&2
  exit 1
}

RESTART=false
DRY_RUN=false

case "${1:-}" in
  "")
    ;;
  --restart)
    RESTART=true
    ;;
  --dry-run)
    DRY_RUN=true
    ;;
  *)
    printf 'Usage: %s [--dry-run|--restart]\n' "$0" >&2
    exit 2
    ;;
esac

if [[ "$SOURCE_ROOT" == "$DEPLOYED_ROOT" ]]
then
  printf 'Source and deployment roots must differ.\n' >&2
  exit 1
fi

if [[ ! -d "$DEPLOYED_ROOT" ]]
then
  printf 'Deployment root does not exist: %s\n' \
    "$DEPLOYED_ROOT" >&2
  exit 1
fi

printf 'Deploying TruePanel\n'
printf '  Source: %s\n' "$SOURCE_ROOT"
printf '  Target: %s\n' "$DEPLOYED_ROOT"

RSYNC_ARGS=(
  -a
  --delete
)

if [[ "$DRY_RUN" == "true" ]]
then
  RSYNC_ARGS+=(
    --dry-run
    --itemize-changes
  )
fi

# bin/ is install-managed. install.sh creates the convenience CLI wrapper there,
# and a source-tree rsync must never delete it merely because the development
# checkout does not contain the generated wrapper.
rsync "${RSYNC_ARGS[@]}" \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='.pytest_cache/' \
  --exclude='.ruff_cache/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='*.bak' \
  --exclude='*.before-*' \
  --exclude='truepanel.backup-*' \
  --exclude='development/logs/' \
  --exclude='development/firmware/lab/' \
  --exclude='bin/' \
  --exclude='truepanel.yaml' \
  "$SOURCE_ROOT/" \
  "$DEPLOYED_ROOT/"

if [[ ! -x "$DEPLOYED_ROOT/start-truepanel.sh" ]]
then
  printf 'Deployment failed: startup script was not copied.\n' >&2
  exit 1
fi

if [[ "$DRY_RUN" == "true" ]]
then
  printf 'Deployment preview complete; no files were changed.\n'
  printf 'Install-managed bin/ content will be preserved.\n'
  exit 0
fi

# Repair the wrapper as part of every real deployment. This makes deployment
# self-healing if an earlier source sync removed bin/ before it became excluded.
install -d -m 0755 "$DEPLOYED_ROOT/bin"
cat > "$DEPLOYED_ROOT/bin/truepanel" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
  pwd
)"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]
then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
  PYTHON_BIN="$(command -v python3 || true)"
fi

if [[ -z "$PYTHON_BIN" ]]
then
  printf 'TruePanel CLI failed: Python is unavailable.\n' >&2
  exit 1
fi

cd "$ROOT_DIR"
exec "$PYTHON_BIN" "$ROOT_DIR/truepanel.py" "$@"
WRAPPER
chmod 0755 "$DEPLOYED_ROOT/bin/truepanel"

printf 'Deployment synchronized successfully.\n'
printf 'CLI wrapper ready: %s\n' "$DEPLOYED_ROOT/bin/truepanel"

mission_control_port() {
  local env_file="${TRUEPANEL_MISSION_ENV_FILE:-/etc/default/truepanel-mission-control}"
  local port='8787'
  local configured=''

  if [[ -r "$env_file" ]]
  then
    configured="$(
      sed -n 's/^[[:space:]]*TRUEPANEL_MC_PORT[[:space:]]*=[[:space:]]*//p' \
        "$env_file" \
      | tail -n 1 \
      | tr -d '[:space:]' \
      || true
    )"
  fi

  if [[ "$configured" =~ ^[0-9]+$ ]]
  then
    port="$configured"
  fi

  printf '%s' "$port"
}

mission_control_probe() {
  local health_url="$1"

  if command -v curl >/dev/null 2>&1
  then
    curl \
      --fail \
      --silent \
      --max-time 2 \
      "$health_url" \
      >/dev/null 2>&1
    return $?
  fi

  if command -v python3 >/dev/null 2>&1
  then
    python3 -c '
import sys
import urllib.request

with urllib.request.urlopen(sys.argv[1], timeout=2) as response:
    raise SystemExit(0 if response.status == 200 else 1)
' "$health_url" >/dev/null 2>&1
    return $?
  fi

  return 127
}

wait_for_mission_control() {
  local port
  local health_url
  local timeout="${TRUEPANEL_DEPLOY_HEALTH_TIMEOUT:-30}"
  local attempt

  if [[ ! "$timeout" =~ ^[0-9]+$ ]] || (( timeout < 1 ))
  then
    printf 'Invalid TRUEPANEL_DEPLOY_HEALTH_TIMEOUT: %s\n' "$timeout" >&2
    return 1
  fi

  port="$(mission_control_port)"
  health_url="${TRUEPANEL_DEPLOY_HEALTH_URL:-http://127.0.0.1:${port}/healthz}"

  printf 'Waiting for Mission Control readiness: %s\n' "$health_url"

  for ((attempt=1; attempt<=timeout; attempt++))
  do
    if mission_control_probe "$health_url"
    then
      printf 'Mission Control ready after %s second(s).\n' "$attempt"
      return 0
    fi

    sleep 1
  done

  printf 'Deployment failed: Mission Control did not become ready within %s seconds.\n' \
    "$timeout" >&2
  printf 'Health endpoint: %s\n' "$health_url" >&2
  return 1
}

if [[ "$RESTART" == "true" ]]
then
  "$DEPLOYED_ROOT/start-truepanel.sh"
  wait_for_mission_control
  printf 'TruePanel services restored and application-ready.\n'
else
  printf 'Services were not restarted.\n'
  printf 'To restore or restart them, run:\n'
  printf '  %s\n' "$DEPLOYED_ROOT/start-truepanel.sh"
fi
