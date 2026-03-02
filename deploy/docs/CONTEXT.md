# Deployment Context

## Goal
Run `GDoc_updater` and the Discord bot on an always-on server so uptime is independent of your laptop.

## Current State (as of 2026-03-02)
- Services currently run from local machine.
- Existing deploy assets:
  - `deploy/REMOTE_SERVER_SETUP.md`
  - `deploy/systemd/gdoc-updater.service`
  - `deploy/env/gdoc-updater.env.example`
- Discord bot currently supports:
  - mention-based queries
  - slash commands (deterministic-only)
  - optional LLM answering for complex mention-based queries
  - optional channel allowlist
  - optional LLM token budget + usage logging

## Constraints
- Must keep local dev workflow intact (edit locally, push, deploy server).
- Secrets must not be committed to git.
- Need a path to scale beyond single process/single host.

## Proposed Target Architecture (Phase 1)
- Single always-on Linux VM.
- Two long-running processes/containers:
  - `gdoc-updater`
  - `discord-bot`
- Environment-driven configuration for paths, tokens, and toggles.
- Runtime data and state stored on server volume (not code dir).
- Log + restart controls for reliability.

## Scalability Path
- Phase 1: single VM + process manager (systemd) or Docker Compose.
- Phase 2: split service configs and independent restart/deploy controls.
- Phase 3: optional migration to managed container platform.

## Data/Secrets Direction
- Store credentials in server env/secrets files.
- Move hardcoded local paths to env-based directories.
- Keep data/state directories explicit and mountable.

## Env Contract (Implemented So Far)
- `FANTASY_DATA_ROOT`: base data root for year folders/calendars.
- `FANTASY_REF_DIR`: directory for yearly `*_CompStats.csv` files.
- `GOOGLE_SERVICE_ACCOUNT_JSON`: path to gspread service-account JSON.
- `ESPN_S2`, `ESPN_SWID`: optional overrides for ESPN auth.
- `YAHOO_KEY`, `YAHOO_SECRET`: optional overrides for Yahoo auth.
- `DISCORD_WEBHOOK_URL`: override for milestone webhook.

Path abstraction module:
- `shared/runtime_config.py`
  - `calendar_csv_path(year)`
  - `comp_stats_csv_path(year)`
  - `draft_results_csv_path(year)`

## Outstanding Risks
- Hardcoded absolute local paths still exist in code.
- Current SSL workaround (`DISCORD_SSL_NO_VERIFY`) should be temporary.
- API quota limits (OpenAI) can disable LLM branch.

## Audit Findings (Hardcoded Paths/Secrets)
- Local absolute paths (`/Users/fano/...`) exist in:
  - `GDoc/GDoc_updater.py`
  - `GDoc/GDoc_Week.py`
  - `StatGenerator.py`
  - `ScheduleGenerator.py`
  - `Models/seasons.py`
  - `Models/Draft.py`
  - `constants.py`
- Hardcoded Google service account path in `constants.py`.
- Hardcoded webhook URL in `discord/discord_messages.py`.
- Credentials currently embedded in `constants.py`:
  - ESPN cookies/tokens
  - Yahoo client credentials
- Existing deploy docs still include local machine path examples that should be generalized for server use.

## Decision Log
- 2026-03-02: start with explicit docs/checklist before refactor.
- 2026-03-02: maintain split accountability: `Codex Tasks` vs `User Tasks`.
- 2026-03-02: completed first-pass hardcoded path/secrets audit; next step is env contract definition.
