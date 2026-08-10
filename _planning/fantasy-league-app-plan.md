# Fantasy League Stats App — Agent Kickoff Plan

## How to use this document

This is a briefing for a coding agent (e.g., Claude Code) that has direct access to the existing Python/pandas codebase and CSV data. Give the agent this file as its starting context, then have it work through Phase 0 before writing any application code. Phase 0 exists because this document was written without direct access to the actual repo — the agent must verify, correct, and fill in every assumption below against the real code and data before proceeding.

---

## 1. Background

This is a long-running NBA fantasy basketball league (8–9 seasons), category-format (9 categories: FG%, FT%, 3PM, PTS, REB, AST, STL, BLK, TO). The scoring format has changed over time — some seasons used traditional head-to-head win/loss matchups, others counted total categories won per week. The league has also moved between platforms (ESPN, Yahoo) across seasons, and roster size/number of members has varied season to season.

The owner has already built a Python/pandas codebase that:
- Ingests historical stats from local CSV files (per-member, per-matchup, per-season, playoffs included)
- Builds "team profile" objects per member
- Computes derived stats (career averages, weighted category ranks, category win/loss records, etc.)
- Currently pushes weekly and all-time results into Google Sheets as the presentation layer (see reference screenshots described in section 2)

The goal now is to replace/extend the Google Sheets presentation layer with a real web app that multiple league members can access on desktop and mobile, with much deeper stat comparison than the sheets currently allow, and optionally per-member login/profiles.

## 2. What the current Google Sheets output looks like (context for the agent)

Two known views exist today:

**Weekly view** — one tab, team-selector dropdown at top shows a single team's raw stat line for the week (FG%, FT%, 3PM, PTS, REB, AST, STL, BLK, TO), plus that team's "Cat Rank" (rank in each category among the league that week) and "Cat Record" (categories won/lost, e.g. 5-4). Below that, a full league table for the week shows every team's raw stats (conditionally color-formatted green/red per category), each team's weekly SCORE (matchup record or category record depending on season format), a computed "Weighted Rank" score, and overall Rank. A scatter plot visualizes Weighted Rank by team.

**Career/season aggregate view** — same structural pattern but for cumulative stats, with an "All Time Career Totals" leader row (best-ever value per category, and who holds it) at top, plus a team selector. This view has multiple tabs: Career Totals, RS (Regular Season) Totals, PO (Playoff) Totals, Career AVGs, RS AVGs, PO AVGs, Career Comparison, and Summary.

The "Weighted Rank" appears to be a normalized composite score across categories (there's a visible hidden helper table converting each raw stat into a per-category scaled rank, 1–10ish, then combining them) — the agent should locate the actual formula/function in the Python codebase rather than guessing from the sheet.

This existing structure is a good source of the initial feature set for the app (it's a proven set of views the league already values) — but the whole point of moving off Sheets is to support more comparisons than a spreadsheet can reasonably hold, so treat this as a floor, not a ceiling.

## 3. Objectives for the app

1. Persist all historical league data (multi-platform, multi-season, regular season + playoffs, weekly matchup-level granularity) in a real backend, not flat CSVs.
2. Reproduce and extend the existing stat views: weekly team cards, league-wide weekly leaderboards, career/season totals and averages, regular season vs. playoff splits, head-to-head history between any two members, category-by-category leaderboards, "best week ever," streaks, etc.
3. Let a user pick any member (or compare 2+ members) and see their stats sliced by season, career, regular season, playoffs, or category.
4. Responsive UI usable on both desktop and mobile.
5. Optional: authentication so each league member can have their own profile/login.
6. Keep the existing Python/pandas logic as the source of truth for stat computation rather than reimplementing it in JS.

## 4. Tech stack recommendation

Quick clarification since the two names look similar but are very different tools:

- **Next.js** — a React framework for building the *frontend* (and, via API routes, light backend endpoints). This is what you want for the UI.
- **NestJS** — a structured Node.js *backend* framework (an alternative to Express), unrelated to React/UI. It would only be relevant if you wanted a large, separately-run Node backend service.

Given the goal of keeping Python/pandas as the stat engine, the recommended split is:

- **Backend / API: Python (FastAPI)** — wraps the existing pandas logic directly. FastAPI gives you REST (or GraphQL, optional) endpoints, is fast to build, and means the existing analysis code doesn't need to be ported to JavaScript at all — it gets called from within the same Python process. This is very likely the biggest leverage decision in this whole plan: it should let the agent reuse most of the existing codebase almost as-is, just wrapped in route handlers instead of a Sheets-writer.
- **Database: Postgres** (SQLite is fine for local dev/prototyping) — CSVs get loaded into normalized tables once via a migration script; the app reads from the DB, not the CSVs, at runtime. Keep the CSVs as the raw/archival source of truth, but stop querying them live.
- **Frontend: Next.js (React, TypeScript)** — server-rendered pages for fast mobile loading, calls the FastAPI backend for data. Deploys easily (Vercel for frontend; Render/Fly.io/Railway for the Python API + Postgres).
- **Auth (if profiles are wanted): NextAuth.js / Auth.js**, or a hosted option like Clerk — simplest way to bolt on per-member login without building auth from scratch.

This avoids NestJS entirely — it would just be duplicate infrastructure next to the Python API for no benefit here.

## 5. Proposed high-level architecture

```
CSV archives (existing)
        │  (one-time / per-season import script)
        ▼
   Postgres database  ←──────────────┐
        │                            │
        ▼                            │
  FastAPI backend (Python)           │
  - reuses existing pandas modules   │
  - exposes REST endpoints per view  │
  - computes derived stats on read   │
    or via a scheduled recompute job │
        │                            │
        ▼                            │
   Next.js frontend (TypeScript)     │
  - member pages, comparisons,       │
    leaderboards, weekly views       │
  - responsive layout for mobile     │
        │                            │
   (optional) NextAuth / Clerk ──────┘
   for member login & profiles
```

## 6. Phase plan

### Phase 0 — Explore and ground-truth (agent does this first, before writing app code)

The agent has access to the real repo; this plan does not. Before building anything, the agent should:

1. Inventory the CSV files: what's in each one, one row = what, which files exist per season/platform, and where the schema is inconsistent across seasons (e.g., ESPN vs. Yahoo exports, category set changes, team count changes, win/loss vs. category-count scoring seasons).
2. Read through the existing Python modules and map: what functions build a "team profile," what functions compute which derived stats (especially the Weighted Rank formula seen in the screenshots), what's already correct and reusable vs. what's Sheets-specific glue code that should be discarded.
3. Identify any hardcoded assumptions in the current code (e.g., fixed 9-category list, fixed number of teams, platform-specific parsing) that will need to become data-driven/configurable for a generalized DB schema.
4. Note data quality issues: missing weeks, mid-season roster changes, ties, incomplete seasons, category set changes across years — these all affect how "career" and "all-time" aggregates should be computed and will need explicit handling rules.
5. Produce a short findings doc (or update this one) summarizing: actual CSV schemas, list of existing reusable functions/modules, the real Weighted Rank formula, and a list of open questions/decisions this raises for the DB schema.

Do not proceed to Phase 1 until this is done and shared back with the owner — several downstream decisions (DB schema, what's "regular season" vs "playoff" per year, how weighted rank is defined) depend on what's actually in the code and data, not on assumptions in this doc.

### Phase 1 — Data layer

- Design normalized Postgres schema: seasons, members (with a stable member identity across platform/season changes), teams (a member's team in a given season), weekly matchups, weekly category results, career/season aggregate tables (or computed views).
- Write a one-time import/ETL script (can live alongside or reuse existing pandas code) to load all historical CSVs into Postgres, preserving regular season vs. playoff distinction and per-season category sets.
- Decide whether aggregates (career totals, weighted ranks) are precomputed and stored, or computed on demand — likely precompute on import/update for read speed, since history doesn't change often except for the current in-progress season.

### Phase 2 — Backend API

- Stand up FastAPI, wire it to Postgres (SQLAlchemy or similar).
- Port the existing derived-stat logic (weighted rank, cat record, etc.) into service functions the API calls — reuse the pandas logic rather than rewriting it.
- Build endpoints mirroring the target views: weekly team view, weekly league table, career totals/averages, RS/PO splits, head-to-head between two members, category leaderboards, "records" (best week, best season, longest streak, etc.).
- Add a lightweight ingestion endpoint or script for updating the current season week-to-week (replacing the Sheets update step).

### Phase 3 — Frontend

- Next.js app with pages/routes for: league home/dashboard, individual member profile (career + season breakdowns), weekly matchup view, head-to-head comparison tool, category leaderboards, all-time records.
- Mobile-first responsive layout (this is a stated requirement).
- Charting (weighted rank scatter, trend lines over a career/season) — reuse a lightweight chart library (e.g., Recharts).

### Phase 4 — Auth / profiles (optional, can be deferred)

- Add NextAuth/Clerk; map logins to existing member identities in the DB.
- Decide what a "profile" adds beyond viewing (e.g., favorite stats pinned, notification prefs) — currently out of scope unless the owner wants it.

### Phase 5 — Deployment & ongoing updates

- Deploy frontend (Vercel) and backend+DB (Render/Fly.io/Railway, or a single VPS).
- Set up the weekly update flow: however stats currently get pulled from ESPN/Yahoo into CSVs, that ingestion step continues, then a script pushes the new week into Postgres instead of Google Sheets.

## 7. Feature ideas beyond the current Sheets (backlog, not required for v1)

- Head-to-head all-time records between any two members
- Category-specific all-time leaderboards (e.g., all-time single-week 3PM record)
- Trend lines per member across seasons (is a manager improving/declining in a category)
- "Manager tendencies" — which categories a member consistently punts or dominates
- Playoff performance vs. regular season performance splits per member
- League-wide record book / awards page

## 8. Open decisions the owner should weigh in on

- Exact definition of "Weighted Rank" — confirm against the real formula in Phase 0 rather than reverse-engineering from the screenshot.
- How to handle category set/scoring format changes across seasons in career aggregates (e.g., a season that didn't track a given category, or used category-count scoring instead of win/loss).
- Whether member identity is stable and already tracked consistently across platforms/seasons in the CSVs, or needs a mapping table.
- Hosting/budget preferences (Vercel + Render/Fly.io are low-cost starting points).
- Whether profiles/auth are v1 or a later addition.
