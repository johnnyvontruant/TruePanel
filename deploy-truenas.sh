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
    systemctl show truepanel.service       --property=WorkingDirectory       --value       --no-pager       2>/dev/null       || true
  )"
fi

if [[ -z "$DEPLOYED_ROOT" ]]
then
  printf '%s\n'     'Could not determine the deployed TruePanel root.'     'Set TRUEPANEL_DEPLOY_ROOT to the persistent installation path.'     >&2
  exit 1
fi

DEPLOYED_ROOT="$(
  cd -- "$DEPLOYED_ROOT" 2>/dev/null
  pwd
)" || {
  printf 'Deployment root does not exist: %s\n'     "$DEPLOYED_ROOT" >&2
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
  exit 0
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
