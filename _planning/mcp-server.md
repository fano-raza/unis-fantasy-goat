# MCP server for the app

Let league members query the league's data from their own AI chat accounts (Claude, ChatGPT, …) by adding the app as an MCP connector. **Status (2026-10-26): v1 live** at `https://134-209-168-108.sslip.io/mcp`. Code in `mcp_server/server.py`, compose service `mcp-server`, Caddy route `/mcp*`. Not yet tested as a real connector inside Claude or ChatGPT (see [Next steps](#next-steps)).

## Decisions (2026-10-26)

- **Access:** open, read-only, no auth (Claude supports authless remote servers). Premium tools left out.
- **Domain:** keep the sslip.io URL for now.
- **Scope:** the user's bar is that questions like "who has the record for most rebounds in week 2" get answered correctly. No StatBot `ask` tool: the AI does the language part, so the tools only need to be expressive and well described. Player-level data is limited to rosters and draft picks.
- **Usage logging:** every tool call is logged with its args (`docker logs unisfantasy-mcp-server | grep tool=`).

## What was built

- `mcp_server/server.py`: `mcp` SDK **2.3** (note: v2 renamed `FastMCP` to `MCPServer` (`mcp.server.mcpserver`); raise `mcp.server.mcpserver.exceptions.ToolError` for messages the AI should see, since any other exception is masked as "Error executing tool X"). Stateless streamable HTTP with JSON responses, port 8091. Per-IP rate limit of 60 requests/min (`MCP_RATE_LIMIT_PER_MIN`), using X-Forwarded-For from Caddy. `/mcp/health`. Pure httpx proxy to `dashboard-api:8090`, with no pandas. Runs at ~66 MB under a 128 MB `mem_limit`.
- **Tools (13):** `league_info` (rules, formats, calendar), `team_week_records` (single-week records, each row carrying the matchup's dates + length in days), `stats_query` (`/query` wrapper), `weekly_results`, `standings`, `team_profile`, `head_to_head`, `records`, `season_stats`, `roster`, `draft`, `playoffs`, `nba_schedule`. Team names match case-insensitively, with a helpful error listing valid names.
- The server `instructions` + tool docstrings carry the league quirks: TO lower-is-better, never sum FG%/FT%, RS vs PO, multi-week matchups (All-Star break; the 2019 playoffs were 14-day rounds, which is why the all-time single-"week" REB record is 812), and the partial current week.
- **Bug fixed along the way (`dashboard_site/api/query_engine.py`):** `/query` counted 2027's pre-seeded placeholder weeks and the not-yet-started current week as 0-0-9 tied matchups (17 phantom draws per team) and as 0-stat weeks (they won "fewest turnovers"). The new `_drop_unplayed` filters rows with no PTS/FGA, on the `/query`/`/timeseries` path only. The website's `/query` consumers (Profile/Comparison wins/losses) were unaffected, since phantom ties add no W/L.

## How to connect (for the league)

Post in Discord:

> **Ask an AI about our league.** You can now add the league's stats to your own Claude chat.
> 1. In Claude (claude.ai or the desktop app), go to **Settings → Connectors → Add custom connector**.
> 2. Name: `Unis Fantasy GOAT`. URL: `https://134-209-168-108.sslip.io/mcp`. No login needed.
> 3. In a chat, make sure the connector is switched on (the tools/"+" menu), then ask away: "who has the most rebounds ever in week 2?", "Fano vs Amil all-time head to head", "who's had the best draft score each year?"
>
> Works on every Claude plan, including Free (Free allows one custom connector). It also works in ChatGPT (Developer Mode, paid plans), Perplexity (paid) and Mistral Le Chat (all plans). Those three haven't been tested by us yet.

**Compatibility (checked 2026-10-26):** Claude (all plans; Free = 1 custom connector, per Anthropic's help center), ChatGPT (Developer Mode, Plus and up, with plan rules in flux), Perplexity (Pro/Max/Enterprise, since 2026-03), Mistral Le Chat (all plans). Not in consumer chat apps: the Gemini app (only Gemini CLI / Gemini Enterprise) and Microsoft Copilot (only via Copilot Studio agents). Developer tools such as Claude Code, Cursor, VS Code and Gemini CLI also work with the URL.

## Next steps

1. **Test as a real connector** in Claude with real questions and compare against the website. The tools were only tested via an MCP client, not with an AI choosing which tool to call.
2. Try ChatGPT (Developer Mode connector); check whether it needs the `search`/`fetch` tool conventions.
3. After a week or two, read the `tool=` logs for errors and questions the tools couldn't answer.
4. ~~Data anomaly~~ **Resolved 2026-10-26: real, not a glitch.** 2026 wk14 Chirayu (33 PTS / 1 TO) and wk15 Rohil (18 PTS / 2 TO), both vs Fano, are **deliberate unset-lineup weeks**: a known league strategy where a manager benches everyone after day 1 to guarantee at least 3 category wins (TO, usually FG%/FT%). The MCP now explains this in `league_info`/server instructions and flags `lineup_unset: true` in `team_week_records` for any completed week under 100 PTS (`UNSET_LINEUP_PTS`; real full weeks are 185+), so future ones get tagged automatically. `team_week_records` also leaves out the in-progress current week by default (its partial totals were topping every "lowest" list). The site's Records page still shows these weeks unflagged; flagging them there is a possible follow-up if the user wants it.
5. Later: a real domain; OAuth for premium tools (phase 2 of the access model).

---

*Original scoping notes (pre-build) follow.*

---

## The idea in one paragraph

A small remote MCP server (HTTPS) that exposes the league's stats as tools an AI can call: standings, weekly results, team profiles, head-to-head, records, career totals, rosters, schedule, and a general stats query. It wraps the existing dashboard API (`dashboard_site/api/app.py`). There's no new data code: every tool is a thin call to an endpoint that already powers the website.

## What already exists (reuse, don't rebuild)

- **Dashboard API**, live at `https://134-209-168-108.sslip.io` (Caddy → `dashboard-api` container on the droplet; Docker-internal base `http://dashboard-api:8090`, which StatBot already uses via `DASHBOARD_API_BASE_URL`).
- **Endpoints worth wrapping** (all in `dashboard_site/api/app.py`):
  - League info: `GET /league/meta` (years, members, current year/week, rs_week_count, categories, season formats, playoff info), `POST /league/week_calendar`.
  - Weekly: `POST /league/weekly_leaderboard`, `POST /league/weekly_team`, `POST /league/weekly_recap`.
  - Standings: `POST /league/standings`, `POST /league/standings_history`, `GET /league/playoff_brackets`, `GET /league/rs_finish_history`.
  - Aggregates: `POST /league/totals`, `POST /league/averages`, `POST /league/leaders`, `POST /league/season_leaders`, `POST /league/records`, `GET /league/category_history`.
  - Teams: `POST /league/team_summary` (career profile fields), `POST /league/head_to_head`.
  - Players/rosters: `POST /league/roster_ranks` (now with `LineupSlot`, IR = "IR"), `GET /league/player_stats` (large, ~2.9 MB, so don't hand it to an AI raw), `POST /league/draft_picks`, `POST /league/nba_schedule`.
  - Generic: `POST /query` (any metric × aggregation × group_by, filtered by years/weeks/teams/opponents/seasons; schema `QueryRequest` in `dashboard_site/api/schemas.py`), `POST /timeseries`, `POST /schedule_swap`.
  - Premium (password-gated): `POST /league/roster_optimizer`, `POST /league/roster_category_odds`, `POST /premium/check_password`. See [roster-optimizer.md](roster-optimizer.md#premium-mode).
- **StatBot's natural-language engine** (`discord/stats_query_engine.py`, `query_parser.py`, `capability_registry.py`, `capability_router.py`, `capability_guide.json`): already turns plain-English questions into answers in Discord. It could back an "ask in plain English" tool, or just serve as a reference for which questions people actually ask (`discord/unanswered_questions.jsonl` lists the ones it couldn't answer).
- **Droplet:** 961 MB RAM, ~230 MB available when last checked (2026-10-26). Fine for a light Python service; don't load pandas/Models in it. Deploy via `deploy/scripts/server_pull_and_restart.sh` (restarts every compose service, then caddy; see memory notes on deploy quirks).

## Proposed shape (to confirm in the new session)

- **Server:** Python, official MCP SDK (`mcp` package, `FastMCP`), streamable-HTTP transport, as a new docker-compose service (e.g. `mcp-server`). It calls `dashboard-api` over the Docker network, so it holds no data of its own.
- **URL:** a Caddy route, e.g. `https://134-209-168-108.sslip.io/mcp` or a dedicated subdomain.
- **Tools (draft list):**
  - `league_info`: members, seasons, categories, scoring format per season, current week, how weeks and the 2 AM ET cutoff work. Every other tool's descriptions should point the AI here first.
  - `weekly_results(year, week)`, `standings(year, week_range)`, `team_profile(team)`, `head_to_head(team_a, team_b)`, `records()`, `career_stats(mode=totals|averages, filters)`, `season_leaders(year, …)`, `roster(team, year)`, `nba_schedule(start, end)`, `playoff_bracket(year)`.
  - `stats_query(...)`: wraps `/query` for anything the fixed tools don't cover.
  - Maybe `ask(question)`, backed by StatBot's engine (see open question 3).
- **Guardrails:** read-only; cap response sizes (trim/round numbers, top-N); per-IP rate limit (Caddy or in-app); clear errors for unknown team names and years.
- **Testing:** MCP Inspector against the local server, then add it as a custom connector in Claude and ask real questions (compare answers to the website).
- **Deliverable for the league:** a short "how to connect" note to post in Discord.

## Open questions (decide with the user first)

1. **Access model.**
   - (a) Open, read-only: anyone with the URL can query. The data is already public on the site.
   - (b) Premium-only: needs real auth. AI connectors don't support a "type the password" prompt, so this means OAuth, a much bigger build.
   - (c) Mixed: stats tools open, premium tools (optimizer, category odds) behind OAuth later.

   Recommendation so far: start with (a), keep (c) as phase 2.
2. **Domain.** Keep the `sslip.io` URL (works today, tied to the droplet's IP) or buy/use a real domain first (looks trustworthy when shared, survives an IP change)? The website itself still has no custom domain either.
3. **Scope beyond the stats tools.**
   - Expose StatBot's plain-English engine as an `ask` tool?
   - Include premium tools at all in v1?
   - Include player-level data (`player_stats`, draft picks), or only team/league data?
4. **Which AI apps to support and test.** Claude is the obvious first. ChatGPT supports custom MCP connectors, but plan and feature availability changes. Verify current docs before promising it to the league (see research items).
5. **Who maintains the connection instructions**, and where they live (Discord pin, a page on the site, both)?
6. **Usage visibility.** Do we want logging of which tools and questions get used (like `unanswered_questions.jsonl` for StatBot), e.g. to find gaps?

## Things to research at the start of the session (unverified)

- **Claude custom connectors:** current requirements for a remote MCP server (transport, whether OAuth is required or optional for an authless server, plan availability, how users add one). Check Anthropic's current docs; don't rely on memory.
- **ChatGPT:** current support for custom MCP connectors (developer mode / connectors / apps), which plans, and any required tool shapes (e.g. `search`/`fetch` conventions for some modes).
- **MCP Python SDK:** current recommended way to run streamable HTTP behind a reverse proxy (Caddy) and in Docker; stateless vs session mode; CORS/host-header settings.
- **Rate limiting:** Caddy has no built-in rate limiter without a plugin, so decide between an in-app limiter and a Caddy module.
- **Memory:** measure the new container's footprint on the droplet before leaving it running (the droplet swaps under pressure).

## Risks / things to watch

- **Wrong answers:** the AI will confidently misread the data if tool descriptions don't explain league specifics: 8 vs 9 categories, TO lower-is-better, RS vs PO, W/L vs category-based seasons, IR players, the 2 AM ET week cutoff, ratings on a 0–1 vs 0–100 scale. `league_info` plus precise tool descriptions are the main defense.
- **Payload size:** some endpoints return big payloads (player_stats ~2.9 MB). Tools must summarize or filter.
- **Droplet load:** an open URL can be hammered, hence the rate limit, and dashboard-api is shared with the live site.
- **Deploy quirk:** every droplet deploy restarts all compose services, including the new one (fine, but expect brief disconnects).

## Suggested first steps for the new session

1. Read this doc and [web-app-build-plan.md](web-app-build-plan.md), and settle open questions 1–3 with the user.
2. Do the research items above (current Claude/ChatGPT connector requirements).
3. Build the server locally against the live API, then test with MCP Inspector.
4. Add the compose service + Caddy route, deploy, and test as a Claude connector with real questions.
5. Write the "how to connect" note, update this doc, and log the session in the build plan.
