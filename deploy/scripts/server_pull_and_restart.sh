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
  # The droplet's disk is small (8.7G) and unused image layers + build
  # cache accumulate across deploys until a build fails outright with
  # "No space left on device" (hit this for real once -- see
  # _planning/web-app-build-plan.md). Pre-emptively clear space before a
  # build if it's already tight, rather than finding out mid-build.
  DISK_USED_PCT="$(df --output=pcent / 2>/dev/null | tail -1 | tr -dc '0-9' || df -h / | tail -1 | awk '{print $5}' | tr -dc '0-9')"
  if [[ -n "$DISK_USED_PCT" ]] && [[ "$DISK_USED_PCT" -ge 85 ]]; then
    echo "[deploy] disk at ${DISK_USED_PCT}% -- pruning docker images/build cache before building"
    docker image prune -a -f || true
    docker builder prune -a -f || true
  fi

  echo "[deploy] restarting docker services"
  docker compose -f infra/docker/docker-compose.yml up -d --build

  # Routine post-deploy cleanup -- every deploy leaves the previous image
  # version's layers unreferenced. Prune them now instead of letting them
  # silently pile up until the next deploy hits the same crisis. Build
  # cache prune here is deliberately NOT `-a` (keeps recently-used cache
  # for faster future builds; only the emergency pre-build branch above
  # does a full `-a` wipe).
  echo "[deploy] pruning unused docker images/build cache"
  docker image prune -a -f || true
  docker builder prune -f || true
else
  echo "[deploy] restarting systemd services"
  sudo systemctl restart gdoc-updater
  sudo systemctl restart discord-bot
fi

echo "[deploy] done"
