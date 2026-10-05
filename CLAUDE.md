# Working notes for this repo

## Web app build — planning routine

The web app rebuild effort is tracked in [`_planning/web-app-build-plan.md`](_planning/web-app-build-plan.md). It holds the decisions made, the repo inventory (what already exists — dashboard_site, DashApp, Discord bot, Models — so it doesn't get rediscovered or duplicated), and the phased task list.

For any work on this effort:
- **Before making changes**, read that doc first to see what's already decided, what already exists, and where the current change fits in the plan.
- **After completing a task or making a notable change/decision**, update the doc: check off the relevant task, add/adjust plan items if scope changed, and append a dated entry to the Session log.

This keeps the plan usable as a real reference across sessions instead of going stale after the first one.

## Local file permissions

No need to ask for permission before creating, editing, overwriting, or deleting local files/folders in this repo, or before running tests/commands that only affect local files. Free rein on local file operations. This does not extend to git push, force-push, or other actions affecting shared/remote state — those still follow normal confirmation rules.

## Web app deploy — pre-authorized

For the web app track specifically (`dashboard_site/` backend, `web/` frontend), the user has pre-authorized automatic deploy after making changes — no need to ask before each one. After a web app change is built and verified (local build passes, live-checked against real data), proceed on your own to:
- Commit the relevant files (scoped `git add` by explicit path, not `-A` — see past session logs for why: this repo tends to have unrelated uncommitted changes sitting in the tree, and `token.json` must never be committed) and push to `origin/main`.
- Deploy the backend to the droplet (`deploy/scripts/server_pull_and_restart.sh` or equivalent — see `_planning/web-app-build-plan.md`'s Phase 5 for the exact commands/URLs). Re-stop `discord-bot` afterward — the deploy restarts every docker-compose service, including it, per a known quirk (see memory).
- Frontend: **`unis-fantasy-goat` (not `web`) is the official production Vercel project** — user confirmed this explicitly. It auto-deploys on every push to `origin/main` via a GitHub integration, so the `git push` above already triggers it; no manual `vercel --prod` needed. If verifying or force-redeploying by hand, use `vercel --prod --scope fano2` (the local `web/.vercel/project.json` is linked to `unis-fantasy-goat`). A second Vercel project named `web` also exists (pre-dates this decision, was the target of every prior session's manual CLI deploys) — left alone for now, not cleaned up. Don't deploy to it going forward; flag to the user if it visibly drifts out of sync.

This covers the web app deploy path only. It does not extend to other destructive/shared-state actions (force-push, deleting branches, deleting the `web` Vercel project, etc.).

## Deploy — pre-authorized repo-wide

As of 2026-08-24, the user extended the above pre-authorization to the whole repo, not just the web app track: whenever the user asks for a change, commit + push + deploy it (droplet restart for backend/bot changes, per `deploy/scripts/server_pull_and_restart.sh`; Vercel auto-deploys the frontend on push) without asking first, unless the user explicitly says not to for that change. Same scoping rules as above still apply: scoped `git add` by explicit path (never `-A`, never `token.json`), verify the change locally first, and re-stop `discord-bot` after a droplet deploy (the compose restart brings it back up as a side effect; it's meant to stay stopped — see memory). This still doesn't cover force-push, branch deletion, or other destructive/shared-state actions outside the normal commit-push-deploy path.

## Discord Mode

Added 2026-10-05, usable in this session and any future one (it's documented here, not as a registered slash command — just say "/discord-mode", "discord mode", or "start discord mode" and follow this).

**What it is**: the user chats to Claude *through Discord* instead of (or alongside) this terminal, via a new `/msg-claude` Discord command (`discord/feature_bot.py`) that logs each message to `msg_claude.md` (`shared.runtime_config.msg_claude_path()`, on the droplet at `/srv/unisfantasy/data/msg_claude.md`) — same Open/Done/Ignored checklist shape as `feature_requests.md`, but a completely separate file/inbox; **Discord Mode never reads `feature_requests.md`**, only `msg_claude.md`.

**On invocation**:
1. If the user didn't specify a scan interval, default to 60 seconds. If they did ("every 2 min"), use that.
2. Start a consecutive-empty-scan counter at 0, and a "phase" of `fast` (the user-specified/default interval).

**Each scan** (use `ScheduleWakeup` to schedule the next one — see below):
1. `ssh root@134.209.168.108 "cat /srv/unisfantasy/data/msg_claude.md"` and look at the `## Open` section.
2. For every unchecked entry: first check whether its content is a stop instruction (e.g. "stop scanning", "stop discord mode", "stop") — if so, mark it Done (step 2b below) and end Discord Mode immediately (`ScheduleWakeup(stop=true)`), telling the user it stopped. Otherwise, treat the quoted message as a new chat turn from the user and respond to it normally, right here in this session's output, as if they'd typed it directly. **Also** post that same reply as a real Discord message, by default to `#bot-test` (`channel_id=1536504604261486774`) unless the message said otherwise, sent via FeatureBot's token (confirmed 2026-10-05 this is the user's explicit preference) -- e.g.:
     ```
     ssh root@134.209.168.108 "docker compose -f /opt/unisFantasyGOAT/infra/docker/docker-compose.yml exec -T feature-bot python3 -c \"
     import os, requests
     requests.post('https://discord.com/api/v10/channels/1536504604261486774/messages', headers={'Authorization': f'Bot {os.getenv(\\\"FEATURE_BOT_TOKEN\\\")}'}, json={'content': '<reply text>'})
     \""
     ```
   - 2b. Once addressed (both the in-session reply and the Discord post are done), mark it off: `ssh root@134.209.168.108 "docker compose -f /opt/unisFantasyGOAT/infra/docker/docker-compose.yml exec -T feature-bot python scripts/mark_msg_claude_done.py '<unique substring>'"` — this moves the line to `## Done` and reacts ✅ on the original Discord message. A 429 from the reaction is transient (Discord rate limit) -- retry once via `scripts._feature_request_ops.react_to_line` directly rather than treating it as a failure.
3. If at least one entry was found/addressed this scan: reset the empty-scan counter to 0 and the phase to `fast` (real activity means Discord Mode stays "active" at the normal cadence, even if it had backed off).
4. If nothing was found this scan: increment the empty-scan counter.
   - While in `fast` phase: once the counter reaches 10, switch to `slow` phase (3600s interval) and reset the counter to 0.
   - While in `slow` phase: once the counter reaches 3, stop entirely (`ScheduleWakeup(stop=true)`) and tell the user Discord Mode ended due to inactivity.
5. Otherwise, call `ScheduleWakeup` with `delaySeconds` = the current phase's interval (clamped to [60, 3600] by the tool itself — the `slow` phase's 3600s is exactly at that ceiling), `noop` = true if nothing was addressed this scan / false if something was, and a `prompt` that restates the current phase + counter explicitly (don't rely on conversation history alone surviving to the next wake) so the next scan picks up correctly, e.g. *"Continue Discord Mode: scan msg_claude.md, interval=60s, phase=fast, consecutive_empty=3/10."*
