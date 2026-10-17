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
  # --remove-orphans: stop/remove containers for services no longer in
  # docker-compose.yml (e.g. gdoc-updater, retired 2026-10-07) instead of
  # leaving them running alongside the current service set.
  docker compose -f infra/docker/docker-compose.yml up -d --build --remove-orphans

  # Caddy resolves dashboard-api's Docker-internal IP once and doesn't
  # notice when a `up -d` recreate gives the container a new one -- it
  # just keeps dialing the old (now dead) IP and 502s every request until
  # Caddy itself restarts. Hit this for real twice in one session
  # (2026-10-16/17): dashboard-api got rebuilt/recreated, Caddy's own
  # image/config was unchanged so compose left it alone, and every
  # request 502'd with "connect: connection refused" until a manual
  # `docker compose restart caddy`. Unconditional on every deploy --
  # restarting Caddy is cheap and this failure mode is silent otherwise.
  echo "[deploy] restarting caddy (picks up dashboard-api's new container IP)"
  docker compose -f infra/docker/docker-compose.yml restart caddy

  # Fail loud, not silent: confirm the public endpoint is actually serving
  # before declaring the deploy done, instead of finding out from a user
  # report later. 20 tries * 3s = up to 60s for the stack to settle.
  echo "[deploy] verifying backend is reachable through caddy"
  DEPLOY_OK=0
  for _ in $(seq 1 20); do
    if curl -sf -o /dev/null --max-time 5 http://localhost/health; then
      DEPLOY_OK=1
      break
    fi
    sleep 3
  done
  if [[ "$DEPLOY_OK" == "1" ]]; then
    echo "[deploy] health check passed"
  else
    echo "[deploy] WARNING: /health did not come back healthy through caddy after 60s -- check 'docker compose logs caddy dashboard-api'"
  fi

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
