# Notion task emoji tagger

A daily automation that gives your TickTick-synced Notion tasks a little
personality. Every night it scans the **`tasks-db`** Notion page's inline
**"All Tasks"** database, finds every **incomplete** task (Checkbox unchecked)
whose title doesn't already start with an emoji, asks Claude for a fitting emoji,
and prepends it to the task title:

```
Buy groceries        ->  🛒 Buy groceries
Email the landlord   ->  📧 Email the landlord
Morning run          ->  🏃 Morning run
```

> Because the Notion ↔ TickTick sync is **bidirectional on the title**, the emoji
> also shows up on the task in TickTick.

## How it works

- [`scripts/tag_tasks_with_emoji.py`](scripts/tag_tasks_with_emoji.py) does the
  work: query Notion → filter → ask Claude for emojis (one batched call) →
  prepend to each title. It is idempotent — titles already starting with an
  emoji are skipped, so re-runs never double-tag.
- [`.github/workflows/notion-emoji-tagger.yml`](.github/workflows/notion-emoji-tagger.yml)
  runs it on a schedule. GitHub cron is UTC with no DST handling, so it triggers
  at **06:00 and 07:00 UTC** and the script's `America/Chicago` guard only does
  work when the local hour is 1 — exactly **1 AM US Central** year-round.

## One-time setup

1. **Create a Notion integration** at <https://www.notion.so/my-integrations>
   (internal integration) and copy its token (`ntn_...`).
2. **Share the database with it:** open the `tasks-db` page in Notion →
   **•••** menu → **Connections** → add your integration. This is required —
   the integration can only see pages explicitly shared with it.
3. **Add GitHub repository secrets** (Settings → Secrets and variables →
   Actions → *New repository secret*):
   - `NOTION_TOKEN` — the integration token from step 1
   - `ANTHROPIC_API_KEY` — an Anthropic API key from <https://console.anthropic.com>

That's it. The scheduled run starts working the next night.

## Testing it

Use the manual trigger first — it defaults to a safe **dry run** (logs intended
changes, writes nothing):

- GitHub → **Actions** → *Notion emoji tagger* → **Run workflow** →
  leave *dry_run* checked → **Run**. Inspect the logs.
- Run it again with *dry_run* **unchecked** to apply the changes, then check a
  few tasks in Notion.

### Running locally

```bash
pip install -r requirements.txt

export NOTION_TOKEN="ntn_..."
export ANTHROPIC_API_KEY="sk-ant-..."
export DRY_RUN=1        # log only, no writes
export FORCE_RUN=1      # bypass the 1 AM Central time guard

python scripts/tag_tasks_with_emoji.py
```

## Configuration

All configuration is via environment variables:

| Variable              | Required | Default                              | Purpose |
|-----------------------|----------|--------------------------------------|---------|
| `NOTION_TOKEN`        | yes      | —                                    | Notion integration token |
| `ANTHROPIC_API_KEY`   | yes      | —                                    | Anthropic API key |
| `TASKS_DB_ID`         | no       | `b971e3b6eebb83cc91450191f70d4278`   | The "All Tasks" database ID |
| `TITLE_PROPERTY`      | no       | `Title`                              | Title property name |
| `COMPLETION_PROPERTY` | no       | `Checkbox`                           | Checkbox property marking completion |
| `DRY_RUN`             | no       | `false`                              | Log changes without writing |
| `FORCE_RUN`           | no       | `false`                              | Skip the 1 AM Central time guard |

---

# Drive-time isochrone map

A small static web map showing how far you can drive from the **Bell County Expo
Center / Cadence Bank Arena** (301 W Loop 121, Belton, TX) in 10 / 20 / 30 / 40 /
60-minute bands. It's a precomputed [Leaflet](https://leafletjs.com) page served
from [`docs/`](docs/) via GitHub Pages — no API key is needed to view it.

**▶ Live map: <https://robz-bdb.github.io/Claude-Cloud/>**

## How it works

- [`scripts/build_isochrones.py`](scripts/build_isochrones.py) calls the
  [OpenRouteService](https://openrouteservice.org) isochrones API **once at build
  time** for the fixed arena origin and writes the nested drive-time bands to
  [`docs/isochrones.geojson`](docs/isochrones.geojson) (a committed, generated
  artifact).
- [`docs/index.html`](docs/index.html) renders that GeoJSON with Leaflet +
  OpenStreetMap tiles: color-graded bands, a marker on the arena, a legend, and
  fit-to-bounds on the 60-minute ring.
- [`.github/workflows/deploy-pages.yml`](.github/workflows/deploy-pages.yml)
  publishes `docs/` to GitHub Pages. It only deploys — it does **not** run the
  build script.

> **Data note:** ORS uses typical road speeds (no live/historical traffic), so
> the bands are a representative, non-rush-hour estimate.

> **Approximate fallback:** if `ORS_API_KEY` is unset, the script emits clearly
> labelled approximate concentric-circle bands (avg 35 mph) so the page always
> renders. The map shows a banner until real data is generated.

## One-time setup

1. **Get a free ORS key** at <https://openrouteservice.org/dev/#/signup>.
2. **Generate the data and commit it:**
   ```bash
   ORS_API_KEY="..." python scripts/build_isochrones.py
   git add docs/isochrones.geojson && git commit -m "Refresh isochrones"
   ```
3. **Enable Pages:** repo Settings → Pages → **Source = "GitHub Actions"**. Pages
   serves from the **default branch (`main`)**, so the site goes live after this
   work is merged.

> Already set up for this repo: Pages is enabled, `main` is the default branch,
> and the live map above auto-republishes on every push to `main` that touches
> `docs/`. To refresh drive times, run the **Build isochrones** workflow (Actions
> → *Build isochrones* → *Run workflow*); it regenerates and commits the GeoJSON.

## Local preview

```bash
python -m http.server 8000 --directory docs
# open http://localhost:8000/
```

## Configuration

| Variable      | Required | Default                       | Purpose |
|---------------|----------|-------------------------------|---------|
| `ORS_API_KEY` | no\*     | —                             | ORS key; if unset, builds approximate circles |
| `ARENA_LAT`   | no       | `31.0305`                     | Origin latitude |
| `ARENA_LON`   | no       | `-97.4787`                    | Origin longitude |
| `RANGES`      | no       | `600,1200,1800,2400,3600`     | Comma-separated seconds (ORS max 3600) |
| `OUTPUT_PATH` | no       | `docs/isochrones.geojson`     | Output file |
| `GEOCODE`     | no       | `false`                       | Resolve origin by geocoding the address |
| `DRY_RUN`     | no       | `false`                       | Log the summary without writing |

\* Not required to *run*, but required to produce real road-network isochrones.
