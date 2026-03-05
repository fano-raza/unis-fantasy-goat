#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/unisFantasyGOAT}"
COMPOSE_FILE="${COMPOSE_FILE:-infra/docker/docker-compose.yml}"

cd "$REPO_DIR"

echo "[smoke] compose ps"
docker compose -f "$COMPOSE_FILE" ps -a

echo
echo "[smoke] gdoc-updater recent logs"
docker compose -f "$COMPOSE_FILE" logs --since=5m --tail=120 gdoc-updater || true

echo
echo "[smoke] discord-bot recent logs"
docker compose -f "$COMPOSE_FILE" logs --since=5m --tail=120 discord-bot || true

echo
echo "[smoke] updater status endpoint"
curl -fsS http://127.0.0.1:5000/status
echo

echo "[smoke] done"
