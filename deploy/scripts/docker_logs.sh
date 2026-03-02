#!/usr/bin/env bash
set -euo pipefail

# Usage: ./deploy/scripts/docker_logs.sh [service]
SERVICE="${1:-}"

if [[ -z "$SERVICE" ]]; then
  docker compose -f infra/docker/docker-compose.yml logs -f
else
  docker compose -f infra/docker/docker-compose.yml logs -f "$SERVICE"
fi
