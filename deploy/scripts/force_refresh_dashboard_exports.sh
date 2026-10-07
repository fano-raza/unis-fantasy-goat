#!/usr/bin/env bash
set -euo pipefail

# Manually force-refresh all of dashboard_site's precomputed CSV exports
# right now, instead of waiting for stat_updater.py's own daily cycle.
# Replaces the dashboard-export half of the retired
# legacy/gdoc/force_refresh_gdoc_week_and_summary.sh (2026-10-07) -- that
# script also pushed to Google Sheets, which this intentionally does not.
#
# Usage:
#   ./deploy/scripts/force_refresh_dashboard_exports.sh 2026

YEAR="${1:-}"

if [[ -z "${YEAR}" ]]; then
  echo "Usage: $0 <year>"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

COMPOSE_FILE="infra/docker/docker-compose.yml"

echo "[refresh] forcing dashboard export refresh: year=${YEAR}"
docker compose -f "${COMPOSE_FILE}" exec -T stat-updater python - <<PY
from scripts.export_real_matchup_flags import main as export_real_matchup_flags
from scripts.export_team_summary import main as export_team_summary
from scripts.export_player_stats import main as export_player_stats
from scripts.export_roster_ranks import main as export_roster_ranks
from scripts.export_nba_schedule import main as export_nba_schedule
from scripts.export_week_calendar import main as export_week_calendar

year = int("${YEAR}")

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

print("Refreshing week calendar...")
export_week_calendar()
print("week_calendar.csv refreshed.")
PY

echo "[refresh] done"
