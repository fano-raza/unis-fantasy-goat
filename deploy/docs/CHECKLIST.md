# Serverization Checklist

Status legend: `todo` | `in_progress` | `done` | `blocked`

## Codex Tasks

1. Create deployment context/checklist docs
- Status: `done`
- Deliverables:
  - `deploy/docs/CONTEXT.md`
  - `deploy/docs/CHECKLIST.md`

2. Audit and inventory hardcoded paths/secrets
- Status: `done`
- Notes:
  - Identify all `/Users/fano/...` references.
  - Identify credential file path assumptions.
  - Findings recorded in `deploy/docs/CONTEXT.md` under `Audit Findings`.

3. Define env-based configuration contract
- Status: `done`
- Notes:
  - Shared env keys for both services.
  - Data directory keys for calendars/stat files/state.
  - Implemented in `shared/runtime_config.py` + `constants.py` env overrides.

4. Refactor updater + season modules to use env paths
- Status: `done`
- Notes:
  - Remove local-machine absolute path dependency.
  - First-pass refactor completed in:
    - `GDoc/GDoc_updater.py`
    - `GDoc/GDoc_Week.py`
    - `Models/seasons.py`
    - `Models/Draft.py`
    - `StatGenerator.py`
    - `ScheduleGenerator.py`
    - `constants.py`

5. Refactor Discord runtime config for server mode
- Status: `done`
- Notes:
  - Ensure all runtime toggles are env-driven.

6. Add service entrypoints and standard run commands
- Status: `done`
- Notes:
  - One stable command for updater.
  - One stable command for discord bot.
  - Implemented:
    - `python -m services.gdoc_updater.entrypoint`
    - `python -m services.discord_bot.entrypoint`

7. Add containerized runtime (optional but preferred)
- Status: `done`
- Notes:
  - Dockerfiles + compose for both services.
  - Implemented under `infra/docker/`.

8. Add/refresh systemd units and env templates
- Status: `done`
- Notes:
  - Keep non-container fallback path.
  - Added:
    - `deploy/systemd/gdoc-updater.service`
    - `deploy/systemd/discord-bot.service`
    - `deploy/env/gdoc-updater.env.example`
    - `deploy/env/discord-bot.env.example`

9. Add operational scripts/docs
- Status: `done`
- Notes:
  - deploy, restart, logs, health checks, backup/restore.
  - Added scripts:
    - `deploy/scripts/server_pull_and_restart.sh`
    - `deploy/scripts/docker_logs.sh`
    - `deploy/scripts/backup_state.sh`
  - Updated runbook:
    - `deploy/REMOTE_SERVER_SETUP.md`

10. End-to-end dry run instructions
- Status: `done`
- Notes:
  - local validation checklist + server cutover checklist.

## User Tasks

1. Choose hosting platform and create always-on server
- Status: `done`
- Needed from you:
  - VM provider + OS choice.
  - Completed: DigitalOcean Ubuntu droplet.

2. Provide server access details
- Status: `done`
- Needed from you:
  - SSH host/user/auth method.
  - Completed: SSH root access to `134.209.168.108`.

3. Provide runtime secrets on server
- Status: `in_progress`
- Needed from you:
  - Discord bot token
  - Google service account credentials
  - Yahoo/ESPN credentials/tokens (if required)
  - OpenAI API key (optional for LLM branch)
- Progress:
  - Google service account JSON uploaded to `/srv/unisfantasy/secrets/google-service-account.json`.

4. Set API billing/limits
- Status: `todo`
- Needed from you:
  - OpenAI budget + hard limits.

5. Provide allowed Discord server/channel IDs (if restrictions desired)
- Status: `done`
- Needed from you:
  - `DISCORD_TEST_GUILD_IDS`
  - `DISCORD_ALLOWED_CHANNEL_IDS`

6. Validate production behavior in Discord + Google Sheets
- Status: `in_progress`
- Needed from you:
  - Confirm slash commands visible
  - Confirm updater writes expected sheet updates

7. Approve local-to-server cutover
- Status: `in_progress`
- Needed from you:
  - When to stop local bot/updater and switch permanently.

## Next Immediate Step
- `in_progress`: pull latest `main` on droplet, rebuild containers, and re-validate `/status` + Discord process stability from fresh logs.

## Session Progress Snapshot (2026-03-04)
- `done`: Docker/Compose installed and running on droplet.
- `done`: repo cloned to `/opt/unisFantasyGOAT`.
- `done`: compose env files created from examples.
- `done`: secrets directory prepared under `/srv/unisfantasy/secrets`.
- `done`: Google service-account file exists and is mounted into containers.
- `done`: import fix applied for `GDoc_Week` package path.
- `done`: import fix applied for `GDoc_AllTime` package path on server copy.
- `done`: required calendar files confirmed present on host under `/srv/unisfantasy/data/2026/`.
- `done`: compose in repo now uses host bind mounts for `/srv/unisfantasy/data`, `/srv/unisfantasy/state`, and `/srv/unisfantasy/secrets`.
- `done`: deterministic analytics coverage expanded; unanswered questions are logged for review.
- `in_progress`: final VM cutover validation (`/status`, slash commands, and sustained process uptime).
