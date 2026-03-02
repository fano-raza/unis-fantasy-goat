# Remote Server Setup (24/7 Updater + Discord Bot)

This runbook gets both services running independently of your laptop:
- `gdoc-updater`
- `discord-bot`

## 1. Prerequisites

- Ubuntu 22.04+ VM/VPS
- SSH sudo access
- Docker + Docker Compose plugin **or** systemd + Python venv
- Repo accessible from server

## 2. Bootstrap server

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip docker.io docker-compose-plugin
sudo useradd -m -s /bin/bash fantasy || true
sudo mkdir -p /opt/unisFantasyGOAT /srv/unisfantasy/{data,state,secrets,backups}
sudo chown -R fantasy:fantasy /opt/unisFantasyGOAT /srv/unisfantasy
```

## 3. Clone repo

```bash
sudo -u fantasy -H bash -lc '
cd /opt/unisFantasyGOAT
if [ ! -d .git ]; then
  git clone <YOUR_REPO_URL> .
else
  git pull
fi
'
```

## 4. Provide data + secrets

Copy required files onto server:
- Google service account JSON -> `/srv/unisfantasy/secrets/google-service-account.json`
- Season calendars -> `/srv/unisfantasy/data/<year>/<year>_matchup_cal.csv`
- Comp stats csvs -> `/srv/unisfantasy/data/ref/<year>_CompStats.csv`

Set strict permissions:

```bash
sudo chown -R fantasy:fantasy /srv/unisfantasy
sudo chmod 700 /srv/unisfantasy/secrets
```

## 5A. Preferred runtime: Docker Compose

### Create env files

```bash
sudo -u fantasy cp /opt/unisFantasyGOAT/infra/docker/env/gdoc-updater.env.example /opt/unisFantasyGOAT/infra/docker/env/gdoc-updater.env
sudo -u fantasy cp /opt/unisFantasyGOAT/infra/docker/env/discord-bot.env.example /opt/unisFantasyGOAT/infra/docker/env/discord-bot.env
```

Edit both env files and fill secrets/IDs.

### Start services

```bash
sudo -u fantasy -H bash -lc '
cd /opt/unisFantasyGOAT
docker compose -f infra/docker/docker-compose.yml up -d --build
'
```

### Logs / status

```bash
docker compose -f /opt/unisFantasyGOAT/infra/docker/docker-compose.yml ps
docker compose -f /opt/unisFantasyGOAT/infra/docker/docker-compose.yml logs -f gdoc-updater
docker compose -f /opt/unisFantasyGOAT/infra/docker/docker-compose.yml logs -f discord-bot
curl http://127.0.0.1:5000/status
```

## 5B. Alternative runtime: systemd + venv

### Install Python deps

```bash
sudo -u fantasy -H bash -lc '
cd /opt/unisFantasyGOAT
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r infra/docker/requirements-deploy.txt
'
```

### Install env files

```bash
sudo mkdir -p /etc/unisfantasy
sudo cp /opt/unisFantasyGOAT/deploy/env/gdoc-updater.env.example /etc/unisfantasy/gdoc-updater.env
sudo cp /opt/unisFantasyGOAT/deploy/env/discord-bot.env.example /etc/unisfantasy/discord-bot.env
sudo chown fantasy:fantasy /etc/unisfantasy/*.env
sudo chmod 600 /etc/unisfantasy/*.env
```

### Install systemd units

```bash
sudo cp /opt/unisFantasyGOAT/deploy/systemd/gdoc-updater.service /etc/systemd/system/
sudo cp /opt/unisFantasyGOAT/deploy/systemd/discord-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable gdoc-updater discord-bot
sudo systemctl start gdoc-updater discord-bot
```

### Logs / status

```bash
systemctl status gdoc-updater --no-pager
systemctl status discord-bot --no-pager
journalctl -u gdoc-updater -f
journalctl -u discord-bot -f
curl http://127.0.0.1:5000/status
```

## 6. Ongoing deploy updates

```bash
sudo -u fantasy -H bash -lc '
cd /opt/unisFantasyGOAT
./deploy/scripts/server_pull_and_restart.sh main
'
```

## 7. Backups

```bash
sudo -u fantasy -H bash -lc '
cd /opt/unisFantasyGOAT
./deploy/scripts/backup_state.sh
'
```

## Notes

- Keep `DISCORD_SSL_NO_VERIFY=0` in production unless cert chain is broken.
- For fast slash command sync, set `DISCORD_TEST_GUILD_IDS`.
- For controlled bot usage, set `DISCORD_ALLOWED_CHANNEL_IDS`.
