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

This covers the web app deploy path only. It does not extend to other destructive/shared-state actions (force-push, deleting branches, deleting the `web` Vercel project, etc.) or to other parts of this repo (Discord bot, GDoc pipeline) — those still follow normal confirmation rules.
