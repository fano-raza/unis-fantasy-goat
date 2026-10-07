# Legacy: Google Sheets ("GDoc") pipeline -- retired 2026-10-07

Everything in this folder pushed league data to Google Sheets, back when
the Sheets workbook was the live presentation layer. It's been fully
superseded by the web app (`dashboard_site/` + `web/`) and is no longer
run anywhere -- the `gdoc-updater` Docker service that ran it has been
removed from `infra/docker/docker-compose.yml`.

This folder is kept only as a historical/reference archive. Nothing in
the live app imports from it.

## What's here

- `GDoc_Week.py`, `GDoc_AllTime.py` -- the actual Sheets-writing functions
  (`updateSheet`, `updateStandings`, `updateCarTotals`, etc.)
- `GDoc_updater.py` -- the old combined update loop (stats + Sheets +
  Discord milestones + draft/roster/player-stats/schedule exports). Its
  non-Sheets responsibilities were ported to `stat_updater.py` (repo
  root), which is now the one production updater.
- `gdoc_auth.py` -- the gspread service-account client + per-year
  spreadsheet name lookup (`gc`, `gDocNames`). Split out of `constants.py`
  so the rest of the app no longer needs Google credentials just to
  import it.
- `service/` -- the Flask entrypoint that used to wrap `GDoc_updater.py`
  for the `gdoc-updater` container.
- `gdoc-updater.service`, `gdoc-updater.env.example.systemd`,
  `gdoc-updater.env.example.docker` -- old systemd/Docker deploy configs.
- `force_refresh_gdoc_week_and_summary.sh` -- the old manual force-refresh
  script (archived, non-functional now that the container is gone). Its
  non-Sheets half lives on as `deploy/scripts/force_refresh_dashboard_exports.sh`.
- `milestone_state.json`, `token.json` -- stale data files that rode along
  with the folder; not read from this location by anything live.

## If GDoc is ever needed again

Re-add a `gdoc-updater`-equivalent service pointing at
`legacy.gdoc.service.entrypoint`, restore the
`GOOGLE_SERVICE_ACCOUNT_JSON` secret/env var, and reinstall `gspread`
(removed from `infra/docker/requirements-deploy.txt`).
