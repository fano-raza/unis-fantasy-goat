# Service Entrypoints

These entrypoints standardize process startup for always-on server deployments.

## gdoc_updater

Run:

```bash
python -m services.gdoc_updater.entrypoint
```

Env:
- `GDOC_UPDATER_HOST` (default `0.0.0.0`)
- `GDOC_UPDATER_PORT` (default `5000`)
- `GDOC_UPDATER_DEBUG` (default `0`)

## discord_bot

Run:

```bash
python -m services.discord_bot.entrypoint
```

Uses existing Discord env contract in `discord/chatbot_bot.py`.
