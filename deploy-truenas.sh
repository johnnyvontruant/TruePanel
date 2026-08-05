#!/usr/bin/env bash

set -euo pipefail

SOURCE_ROOT="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
  pwd
)"

DEPLOYED_ROOT="${TRUEPANEL_DEPLOY_ROOT:-/mnt/SSDs/Applications/TruePanel}"

RESTART=false

if [[ "${1:-}" == "--restart" ]]
then
  RESTART=true
elif [[ -n "${1:-}" ]]
then
  printf 'Usage: %s [--restart]\n' "$0" >&2
  exit 2
fi

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

rsync -a \
  --delete \
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
  --exclude='truepanel.yaml' \
  "$SOURCE_ROOT/" \
  "$DEPLOYED_ROOT/"

if [[ ! -x "$DEPLOYED_ROOT/start-truepanel.sh" ]]
then
  printf 'Deployment failed: startup script was not copied.\n' >&2
  exit 1
fi

printf 'Deployment synchronized successfully.\n'

if [[ "$RESTART" == "true" ]]
then
  "$DEPLOYED_ROOT/start-truepanel.sh"
else
  printf 'Services were not restarted.\n'
  printf 'To restore or restart them, run:\n'
  printf '  %s\n' "$DEPLOYED_ROOT/start-truepanel.sh"
fi
