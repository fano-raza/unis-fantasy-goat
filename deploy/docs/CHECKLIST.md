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
- Status: `in_progress`
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
- Status: `todo`
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
- Status: `todo`
- Notes:
  - local validation checklist + server cutover checklist.

## User Tasks

1. Choose hosting platform and create always-on server
- Status: `todo`
- Needed from you:
  - VM provider + OS choice.

2. Provide server access details
- Status: `todo`
- Needed from you:
  - SSH host/user/auth method.

3. Provide runtime secrets on server
- Status: `todo`
- Needed from you:
  - Discord bot token
  - Google service account credentials
  - Yahoo/ESPN credentials/tokens (if required)
  - OpenAI API key (optional for LLM branch)

4. Set API billing/limits
- Status: `todo`
- Needed from you:
  - OpenAI budget + hard limits.

5. Provide allowed Discord server/channel IDs (if restrictions desired)
- Status: `todo`
- Needed from you:
  - `DISCORD_TEST_GUILD_IDS`
  - `DISCORD_ALLOWED_CHANNEL_IDS`

6. Validate production behavior in Discord + Google Sheets
- Status: `todo`
- Needed from you:
  - Confirm slash commands visible
  - Confirm updater writes expected sheet updates

7. Approve local-to-server cutover
- Status: `todo`
- Needed from you:
  - When to stop local bot/updater and switch permanently.

## Next Immediate Step
- `in_progress`: Codex task #8 (refresh systemd + env templates for new service entrypoints)
