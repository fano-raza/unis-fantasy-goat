# Deployment Context

## Goal
Run `gdoc-updater` and the Discord bot on an always-on server so uptime is independent of your laptop.

## Current State (as of 2026-03-04)
- Infrastructure selected: Docker Compose on a DigitalOcean Ubuntu VM (`134.209.168.108`).
- Repo cloned on server at `/opt/unisFantasyGOAT`.
- Runtime directories created:
  - `/srv/unisfantasy/data`
  - `/srv/unisfantasy/state`
  - `/srv/unisfantasy/secrets`
  - `/srv/unisfantasy/backups`
- Compose env files created:
  - `infra/docker/env/discord-bot.env`
  - `infra/docker/env/gdoc-updater.env`
- Google service account JSON uploaded to:
  - `/srv/unisfantasy/secrets/google-service-account.json`
- Compose file in repo now uses host bind mounts for persistent data/state:
  - `/srv/unisfantasy/data:/srv/unisfantasy/data`
  - `/srv/unisfantasy/state:/srv/unisfantasy/state`
  - `/srv/unisfantasy/secrets:/srv/unisfantasy/secrets:ro`
- Discord analytics engine has expanded deterministic intent support and unanswered-question logging.

## What Is Already Working
- Discord bot container can start with mounted secrets/data and env contract.
- Secret mount path is visible inside containers:
  - `/srv/unisfantasy/secrets/google-service-account.json`
- Docker networking and published port `5000` are configured.

## Current Blocking Issue
- No known code-level import blocker in current repo head.
- Main operational risk is server drift (droplet running an older checkout or stale compose/image).

## Immediate Next Commands (Resume Here)
Run on server in `/opt/unisFantasyGOAT`:

```bash
git fetch origin main
git checkout main
git pull --ff-only origin main
docker compose -f infra/docker/docker-compose.yml up -d --build
sleep 8
docker compose -f infra/docker/docker-compose.yml ps -a
docker compose -f infra/docker/docker-compose.yml logs --since=5m --tail=160 gdoc-updater
docker compose -f infra/docker/docker-compose.yml logs --since=5m --tail=160 discord-bot
curl -sS http://127.0.0.1:5000/status
```

If next error is missing data files, sync local data root to server:

```bash
rsync -avh --progress --exclude "unisFantasyGOAT/" \
  "/Users/fano/Documents/Fantasy/Fantasy GOAT/" \
  root@134.209.168.108:/srv/unisfantasy/data/
```

## Data/Secrets Contract
- `GOOGLE_SERVICE_ACCOUNT_JSON=/srv/unisfantasy/secrets/google-service-account.json`
- `FANTASY_DATA_ROOT=/srv/unisfantasy/data`
- `FANTASY_REF_DIR=/srv/unisfantasy/ref` (or wherever `*_CompStats.csv` are staged)

## Risks / Cleanups
- `discord/discord_messages.py` webhook URL has been exposed; rotate in Discord and update env/config.
- `constants.py` still contains embedded third-party credentials; migrate to env-only values.
- If server still reports Compose `version` warning, its checkout is stale and needs pull/restart.

## Decision Log
- 2026-03-02: Use Docker Compose as Phase 1 deployment.
- 2026-03-02: Keep data/secrets outside repo under `/srv/unisfantasy/*`.
- 2026-03-04: Standardize on host bind mounts (no named volumes) for data/state/secrets.
- 2026-03-04: Keep deterministic analytics in bot runtime; unanswered intents logged for periodic review.
