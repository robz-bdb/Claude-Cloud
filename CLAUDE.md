# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Two small, independent components:

1. **Notion emoji tagger** — a scheduled automation that tags incomplete Notion
   tasks with a contextually-chosen emoji once a day.
2. **Drive-time isochrone map** — a precomputed static Leaflet page (in `docs/`)
   showing 10/20/30/40/60-minute drive-time bands around the Bell County Expo
   Center, deployed to GitHub Pages.

There is no app server or test suite. Each component is one Python script plus a
GitHub Actions workflow.

## Commands

```bash
pip install -r requirements.txt

# Dry run locally (logs intended changes, writes nothing; skips the time guard)
DRY_RUN=1 FORCE_RUN=1 NOTION_TOKEN=... ANTHROPIC_API_KEY=... \
  python scripts/tag_tasks_with_emoji.py

# Real run locally
FORCE_RUN=1 NOTION_TOKEN=... ANTHROPIC_API_KEY=... \
  python scripts/tag_tasks_with_emoji.py
```

There is no build step, linter config, or test runner in the repo. Manual runs
go through the GitHub Actions UI (*Notion emoji tagger* → Run workflow), which
defaults to a dry run.

## Architecture

Two pieces, both intentionally small:

- **`scripts/tag_tasks_with_emoji.py`** — the whole pipeline, configured entirely
  via environment variables (no flags). Flow: query Notion for incomplete tasks →
  drop empty/already-emoji titles → one batched Anthropic call returns an emoji
  per title → `PATCH` each page's title. It talks to the Notion REST API directly
  (not the MCP connector, which is interactive-session-only) and to Claude via the
  `anthropic` SDK.
- **`.github/workflows/notion-emoji-tagger.yml`** — the scheduler. Installs deps
  and runs the script with secrets in env.

### Things that are easy to get wrong

- **The target is an inline database, not the page.** `tasks-db`
  (`34a1e3b6eebb81b1af05faeabce55b6c`) is a *page* that wraps the **"All Tasks"**
  database (`b971e3b6eebb83cc91450191f70d4278`). `TASKS_DB_ID` must be the
  database ID, which is what the Notion query endpoint needs.
- **"Incomplete" = `Checkbox` unchecked.** This DB is the standard TickTick
  "Integrate Notion" schema: title property is `Title`, completion is a
  `checkbox` named `Checkbox` (no Status property). The query filters on it
  server-side.
- **Title sync is bidirectional with TickTick.** Editing `Title` in Notion
  changes the TickTick task too. That's intended (emoji shows up in both), but it
  means title writes are not cosmetic-only — be deliberate about changing them.
- **Idempotency depends on the leading-emoji regex** (`starts_with_emoji`). Tasks
  whose title already starts with an emoji are skipped, which is what keeps daily
  re-runs from stacking emojis. Preserve this guard.
- **DST-safe scheduling is split between cron and code.** The cron fires at both
  06:00 and 07:00 UTC; `within_run_window()` (America/Chicago, hour == 1) ensures
  exactly one effective run at 1 AM Central. Manual `workflow_dispatch` sets
  `FORCE_RUN=1` to bypass that guard. Don't "simplify" the double cron without
  also handling DST.

### Drive-time isochrone map

- **`scripts/build_isochrones.py`** — env-configured (no flags), mirrors the
  tagger's style. Flow: parse ranges → resolve origin → one ORS isochrones call →
  normalize/sort features (adding `minutes`/`label`/`color`) → write
  `docs/isochrones.geojson`. Builds approximate concentric circles when
  `ORS_API_KEY` is unset.
- **`docs/index.html`** — self-contained Leaflet page (CDN), no build step.
- **`.github/workflows/deploy-pages.yml`** — publishes `docs/`; deploy-only.

Things that are easy to get wrong here:

- **ORS auth uses the raw key in `Authorization`** — no `Bearer` prefix (unlike
  the Notion script).
- **Coordinate order differs:** ORS/GeoJSON are `[lon, lat]`; Leaflet is
  `[lat, lon]`. Most common bug — both files call it out.
- **Bands are nested full polygons, not rings.** The page paints them
  minutes-descending (60 → 10) with semi-transparent fills so inner zones sit on
  top; don't switch to difference geometry. The script writes a `color` per
  feature so HTML and data never disagree.
- **`docs/isochrones.geojson` is a committed generated artifact** — don't gitignore
  it. Regenerating needs an ORS key; viewing never does.
- **ORS free-tier driving-car max is 3600s (60 min).** The script warns past that;
  ORS will reject larger ranges.
- **Pages serves from the default branch**, so map changes go live after merge.
  Keep the `paths:` filter so tagger-only pushes don't redeploy.

## Conventions

- Per-page update failures are caught and logged so one bad task never aborts the
  batch; preserve that resilience.
- Notion writes are throttled (~3 req/s) — keep the small sleep between `PATCH`es.
- Model is `claude-haiku-4-5-20251001` with a cached system prompt and a single
  batched request for all titles; keep it to one call rather than per-task.
- Secrets (`NOTION_TOKEN`, `ANTHROPIC_API_KEY`) come from env / GitHub Actions
  secrets only. The full setup (Notion integration, sharing the DB, adding repo
  secrets) is in `README.md`.
