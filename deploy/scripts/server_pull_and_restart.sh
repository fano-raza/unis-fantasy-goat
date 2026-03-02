#!/usr/bin/env bash
set -euo pipefail

# Usage: ./deploy/scripts/server_pull_and_restart.sh [branch]
BRANCH="${1:-main}"

REPO_DIR="${REPO_DIR:-/opt/unisFantasyGOAT}"
USE_DOCKER="${USE_DOCKER:-1}"

cd "$REPO_DIR"

echo "[deploy] fetching latest from $BRANCH"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

if [[ "$USE_DOCKER" == "1" ]]; then
  echo "[deploy] restarting docker services"
  docker compose -f infra/docker/docker-compose.yml up -d --build
else
  echo "[deploy] restarting systemd services"
  sudo systemctl restart gdoc-updater
  sudo systemctl restart discord-bot
fi

echo "[deploy] done"
