#!/usr/bin/env bash
set -euo pipefail

echo "== TruePanel Docker Installer =="

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker was not found. Please install Docker or use TrueNAS Apps/Dockge."
  exit 1
fi

echo "Checking hardware..."
./detect.sh || true

echo
echo "Building TruePanel container..."
docker compose build

echo
echo "Starting TruePanel..."
docker compose up -d

echo
echo "TruePanel is running."
echo
echo "Useful commands:"
echo "  docker compose logs -f"
echo "  docker compose restart"
echo "  docker compose down"
