# Working notes for this repo

## Web app build — planning routine

The web app rebuild effort is tracked in [`_planning/web-app-build-plan.md`](_planning/web-app-build-plan.md). It holds the decisions made, the repo inventory (what already exists — dashboard_site, DashApp, Discord bot, Models — so it doesn't get rediscovered or duplicated), and the phased task list.

For any work on this effort:
- **Before making changes**, read that doc first to see what's already decided, what already exists, and where the current change fits in the plan.
- **After completing a task or making a notable change/decision**, update the doc: check off the relevant task, add/adjust plan items if scope changed, and append a dated entry to the Session log.

This keeps the plan usable as a real reference across sessions instead of going stale after the first one.

## Local file permissions

No need to ask for permission before creating, editing, overwriting, or deleting local files/folders in this repo, or before running tests/commands that only affect local files. Free rein on local file operations. This does not extend to git push, force-push, or other actions affecting shared/remote state — those still follow normal confirmation rules.
