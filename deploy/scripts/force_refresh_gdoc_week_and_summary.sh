#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./deploy/scripts/force_refresh_gdoc_week_and_summary.sh 2026 21
#
# Runs inside gdoc-updater container:
# 1) updateSheet(year, week)
# 2) Rebuild all-time sheets + summary using fresh league state

YEAR="${1:-}"
WEEK="${2:-}"

if [[ -z "${YEAR}" || -z "${WEEK}" ]]; then
  echo "Usage: $0 <year> <week>"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

COMPOSE_FILE="infra/docker/docker-compose.yml"

echo "[refresh] forcing week update: year=${YEAR} week=${WEEK}"
docker compose -f "${COMPOSE_FILE}" exec -T gdoc-updater python - <<PY
from GDoc.GDoc_Week import updateSheet
from Models.League import fantasyLeague
from GDoc.GDoc_AllTime import (
    updateCarTotals, updateRSTotals, updatePOTotals,
    updateCarAVGs, updateRSAVGs, updatePOAVGs, updateSummarySheet
)
from scripts.export_real_matchup_flags import main as export_real_matchup_flags
from scripts.export_team_summary import main as export_team_summary
from scripts.export_player_stats import main as export_player_stats
from scripts.export_roster_ranks import main as export_roster_ranks
from scripts.export_nba_schedule import main as export_nba_schedule

year = int("${YEAR}")
week = int("${WEEK}")

print(f"Running updateSheet({year}, {week})...")
updateSheet(year, week)
print("Week sheet updated.")

print("Rebuilding all-time tables + summary...")
league = fantasyLeague()
updateCarTotals(league)
updateRSTotals(league)
updatePOTotals(league)
updateCarAVGs(league)
updateRSAVGs(league)
updatePOAVGs(league)
updateSummarySheet(league)
print("All-time tables + summary updated.")

print("Refreshing dashboard_site real_matchup lookup...")
export_real_matchup_flags()
print("real_matchup_flags.csv refreshed.")

print("Refreshing dashboard_site team summary...")
export_team_summary()
print("team_summary.csv refreshed.")

print("Refreshing real NBA player stats...")
export_player_stats()
print("player_stats.csv refreshed.")

print("Refreshing roster/rank snapshot...")
export_roster_ranks([year])
print("roster_ranks.csv refreshed.")

print("Refreshing NBA schedule...")
export_nba_schedule()
print("nba_schedule.csv refreshed.")
PY

echo "[refresh] done"
