# Discord Stats Chatbot Setup Checklist

This checklist reflects the current implementation in `discord/` and the manual steps you still need to complete.

## Implemented in code

- `discord/discord_messages.py` (moved from `GDoc/`)
- `discord/chatbot_bot.py`
- `discord/query_parser.py`
- `discord/stats_query_engine.py`

### Query capabilities now supported

- Leader queries (`most` / `least`) with optional top-N
- Standings queries (`W/L` or `category` standings)
  - Natural phrasing supported (e.g., `who is currently in first place in the league?`)
- Team vs team comparisons
- Head-to-head record summaries
- Team season summaries
- Week-specific and week-range stat leaders
- Broad/free-form analysis fallback via LLM context answering (if `OPENAI_API_KEY` is set)
  - Hybrid behavior:
    - Simple place/rank questions stay deterministic and concise.
    - Complex/open-ended statistical questions use LLM with grounded data context.
    - For LLM ranking questions, responses include the requested rank result plus a full ordered ranking list.

### Input modes now supported

- Mention-based natural language chat
- Slash commands:
  - `/ask_stats`
  - `/standings`
  - `/leader`
  - `/compare`
  - `/head_to_head`
  - `/team_summary`
  - All slash commands run in deterministic-only mode (no LLM usage).

## Manual setup required

1. Create Discord app + bot
- Go to Discord Developer Portal.
- Create application and add bot user.
- Copy bot token.

2. Enable intents
- Enable `MESSAGE CONTENT INTENT` in Bot settings.

3. Invite bot to your server
- OAuth2 scopes: `bot`, `applications.commands`
- Permissions: `View Channels`, `Send Messages`, `Read Message History`

4. Install dependencies (project `.venv`)
```bash
./.venv/bin/python -m pip install disnake openai pandas gspread
```

- Status: `disnake` and `openai` are already installed in this repo venv.

5. Set environment variables
- Required:
  - `DISCORD_BOT_TOKEN=<your_discord_bot_token>`
- Recommended:
  - `OPENAI_API_KEY=<your_openai_api_key>`
  - `DISCORD_QA_MODEL=gpt-4.1-mini`
  - `DISCORD_TEST_GUILD_IDS=<comma-separated guild ids for instant slash sync>`
  - `DISCORD_ALLOWED_CHANNEL_IDS=<comma-separated channel ids to allow bot responses>`
  - `DISCORD_LLM_MAX_TOKENS_MONTH=<monthly token cap for LLM>` (set `0` for unlimited)
  - `DISCORD_LLM_MAX_OUTPUT_TOKENS=<per-response cap>` (default `300`)
  - `DISCORD_LLM_LOG_REQUESTS=<1 to log token usage per LLM call>`
  - `DISCORD_LLM_LOG_MAX_QUESTION_CHARS=<question preview length in logs>`

Seamless local setup (recommended):
```bash
cp discord/.env.example discord/.env
```
Then edit `discord/.env` with your real token/key.

Slash command registration speed:
- If `DISCORD_TEST_GUILD_IDS` is set, slash commands register quickly in those guild(s).
- If not set, commands are global and may take time to appear.

Channel restrictions:
- If `DISCORD_ALLOWED_CHANNEL_IDS` is set, mention responses and slash commands only work in those channel IDs.
- If not set, the bot can respond in any channel where it has permissions.

6. Run bot
```bash
python3 -m discord.chatbot_bot
```

If you hit a TLS/certificate error when connecting to Discord:
- The bot now auto-uses the `certifi` CA bundle at startup.
- The bot also forces an explicit `aiohttp` SSL connector using that CA bundle.
- Ensure `certifi` is installed in the same venv.
- Temporary troubleshooting fallback only:
  - Set `DISCORD_SSL_NO_VERIFY=1` in `discord/.env` to bypass TLS certificate verification.
  - Remove it once certificates are fixed.

## Usage examples

Mention-based:
- `@YourBot in 2020 who had the most points?`
- `@YourBot top 3 rebounders in 2026 regular season`
- `@YourBot compare Fano vs Ange in 2026 for assists`
- `@YourBot head to head Fano vs Sama in 2025`
- `@YourBot week 6 steals leader in 2024`
- `@YourBot weeks 3 to 8, who scored the most points in 2026?`
- `@YourBot show 2026 category standings`
- `@YourBot who is currently in first place in the league?`

Slash command examples:
- `/ask_stats question:"in 2026, who had the most assists in playoffs?"`
- `/leader year:2026 stat:PTS scope:RS top_n:5 direction:max`
- `/standings year:2026 format:cats`
- `/compare year:2026 team1:Fano team2:Ange scope:ALL stat:REB`
- `/head_to_head year:2026 team1:Fano team2:Sama scope:RS`
- `/team_summary year:2026 team:Fano scope:ALL`

## Important constraints

- Data availability is limited to years present in `constants.seasonInfo`.
- Team names are matched to known league member names.
- Some very open-ended prompts may require LLM fallback (`OPENAI_API_KEY`) to answer well.
- For true "any analysis" support, keep prompts explicit with year/scope/stat/team when possible.
- Monthly LLM token usage can be capped via `DISCORD_LLM_MAX_TOKENS_MONTH`.
- Real measured LLM token usage is tracked in:
  - `discord/llm_usage_state.json` (monthly running total)
  - `discord/llm_request_log.jsonl` (per-call logs when enabled)
- Slash commands never call LLM; they are fully deterministic by design.

## Always-on deployment checklist

- Run this bot on an always-on VM/server.
- Create a dedicated `systemd` service for `python3 -m discord.chatbot_bot`.
- Inject env vars via service environment file.
- Use restart policy (`Restart=always`) and monitor logs via `journalctl`.
