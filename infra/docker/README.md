# Docker Runtime

## Files
- `infra/docker/Dockerfile`
- `infra/docker/docker-compose.yml`
- `infra/docker/env/gdoc-updater.env.example`
- `infra/docker/env/discord-bot.env.example`

## Quick start
1. Copy env templates:
```bash
cp infra/docker/env/gdoc-updater.env.example infra/docker/env/gdoc-updater.env
cp infra/docker/env/discord-bot.env.example infra/docker/env/discord-bot.env
```

2. Fill in secrets and IDs.

3. Start services:
```bash
docker compose -f infra/docker/docker-compose.yml up -d --build
```

4. Logs:
```bash
docker compose -f infra/docker/docker-compose.yml logs -f gdoc-updater
docker compose -f infra/docker/docker-compose.yml logs -f discord-bot
```
