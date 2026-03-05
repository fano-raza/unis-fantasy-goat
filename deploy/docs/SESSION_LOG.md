# Session Log

Use this file as the primary resume point for deployment progress.
When asked to "resume where we left off", start from the latest entry here.

## 2026-03-02

### Completed
- Provisioned DigitalOcean Ubuntu droplet at `134.209.168.108`.
- Installed Docker/Compose and created runtime directories under `/srv/unisfantasy/`.
- Cloned repo to `/opt/unisFantasyGOAT`.
- Created compose env files from examples under `infra/docker/env/`.
- Uploaded Google service-account JSON to:
  - `/srv/unisfantasy/secrets/google-service-account.json`
- Mounted secrets path into containers and verified file visibility.
- Fixed one package import issue in updater (`GDoc_Week` path).
- Fixed second updater import issue on server copy (`GDoc_AllTime` path).
- Captured deployment state in:
  - `deploy/docs/CONTEXT.md`
  - `deploy/docs/CHECKLIST.md`

## 2026-03-04

### Completed
- Added deterministic analytics planning artifacts for chatbot capability expansion:
  - `analytics/analytics_question_bank.md`
  - `analytics/analytics_capabilities.yaml`
  - `analytics/analytics_goldens.jsonl`
- Added reusable recap generator tooling and renderer updates:
  - `recaps/recap_utils.py`
  - `recaps/generate_recap.py`
- Generated regular-season recap output with table-based formatting:
  - `recaps/2026_regular_season_recap.md`
- Wired deterministic capability routing + analytics handlers into Discord pipeline:
  - `discord/capability_router.py`
  - updates in `discord/query_parser.py`
  - updates in `discord/stats_query_engine.py`
- Added golden routing test runner:
  - `analytics/run_golden_tests.py`
- Verified regression status:
  - Initial: `27/27` implemented-intent checks passed, `12` advanced intents skipped
  - Updated: fully implemented skipped set (`mvp_by_avg_rating`, `strength_of_schedule`, `draft_pick_value`, `draft_team_score`, `correlation_scan`, `trend_split`, `consistency`, `what_if_schedule_swap`, `recap_regular_season`)
  - Current: `39/39` passed, `0` skipped

### Code Updates (Deterministic #1 Completion)
- Completed handler wiring for advanced intents in:
  - `discord/stats_query_engine.py`
- Added scope default refinement for MVP/rating phrasing in:
  - `discord/capability_router.py`
- Updated golden runner alias/param normalization for mixed `scope` vs `year_range` expectations in:
  - `analytics/run_golden_tests.py`
- Added deterministic recency-weighted title projection intent:
  - routing in `discord/capability_router.py` (`predict_champion`)
  - parser intent support in `discord/query_parser.py`
  - scoring model in `discord/stats_query_engine.py`
  - tuning env var: `DISCORD_RECENCY_HALF_LIFE_WEEKS` (default `4`)
- Added unanswered-question capture for periodic capability review:
  - logger module `discord/unanswered_log.py`
  - wired no-answer paths in `discord/stats_query_engine.py`
  - output file: `discord/unanswered_questions.jsonl`
  - optional disable env var: `DISCORD_UNANSWERED_LOG_DISABLE=1`

### Notes
- Analytics files are intended as the source of truth for deterministic routing and regression tests.
- Goldens currently encode intent/parameter expectations and response constraints (`must_include`, `must_not_include`).

### Current Blocker
- `gdoc-updater` container restart loop due to Docker volume mapping mismatch:
  - host has `/srv/unisfantasy/data/2026/2026_matchup_cal.csv`
  - container did not see it because compose used named volume `fantasy-data` at `/srv/unisfantasy/data`
  - root cause confirmed with:
    - `docker compose ... run --rm gdoc-updater ls -l /srv/unisfantasy/data/2026/2026_matchup_cal.csv`
    - output: `No such file or directory`

### Next Commands
Update compose to host bind mounts, then restart:

```bash
cd /opt/unisFantasyGOAT
# ensure infra/docker/docker-compose.yml has:
# - /srv/unisfantasy/data:/srv/unisfantasy/data
# - /srv/unisfantasy/state:/srv/unisfantasy/state
# - /srv/unisfantasy/secrets:/srv/unisfantasy/secrets:ro
docker compose -f infra/docker/docker-compose.yml up -d --build
sleep 8
docker compose -f infra/docker/docker-compose.yml ps -a
docker compose -f infra/docker/docker-compose.yml logs --tail=120 gdoc-updater
docker compose -f infra/docker/docker-compose.yml run --rm gdoc-updater ls -l /srv/unisfantasy/data/2026/2026_matchup_cal.csv
curl http://localhost:5000/status
```

## 2026-03-04 (VM Focus Refresh)

### Completed
- Confirmed `infra/docker/docker-compose.yml` in repo now uses host bind mounts:
  - `/srv/unisfantasy/data:/srv/unisfantasy/data`
  - `/srv/unisfantasy/state:/srv/unisfantasy/state`
  - `/srv/unisfantasy/secrets:/srv/unisfantasy/secrets:ro`
- Refreshed deployment docs to remove stale `GDoc_AllTime` import blocker.
- Updated checklist status for current deployment phase.

### Current Focus
- Final VM cutover validation from latest repo head on droplet.
- Ensure both containers stay stable and `/status` returns successfully.

### Resume Commands (Server)
```bash
cd /opt/unisFantasyGOAT
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
