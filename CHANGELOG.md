# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Restructured the repo into a pop-in Claude Code sandbox** — a monorepo of
  small, independent projects under `projects/<name>/`, one project per context
  window. The Notion emoji tagger moved from the repo root into
  `projects/notion-emoji-tagger/` (script, `requirements.txt`, `README.md`, and
  project `CLAUDE.md`), with no change to its logic; the `Notion emoji tagger`
  workflow now runs with `working-directory: projects/notion-emoji-tagger`.
- **Added** a sandbox-wide root `CLAUDE.md` (conventions + new-project protocol),
  a rewritten root `README.md`, a `projects/_template/` scaffold, and a `shared/`
  helper package (`sandbox.env`, `sandbox.clients`) so projects share env loading,
  API clients, and keys (`.env.example`) instead of duplicating them.

### Removed

- **Moved** the entire drive-time isochrone map out of this repo into
  [`robz-bdb/stampede-hockey-mapping`](https://github.com/robz-bdb/stampede-hockey-mapping)
  (live map now at <https://robz-bdb.github.io/stampede-hockey-mapping/>). The map's
  scripts (`build_isochrones.py`, `build_population.py`), the `docs/` site, and the
  `Build isochrones` / `Build population` / `Deploy Pages` workflows were deleted here,
  and the build-time `geopandas`/`shapely`/`pyproj` dependencies dropped. This repo now
  contains only the Notion emoji tagger. The isochrone entries below (including the
  in-progress Growth tab) record work done while the map still lived here.

### Drive-time isochrone map

- **Added** a **Growth** tab to the map — small-multiple census-tract heat maps (one
  per available year) shading each of ~540 tracts by its % population growth since
  2010, so you can see *where* the area grew (the Williamson County / I-35 corridor
  stands out). New committed artifact `docs/growth_tracts.geojson` (~0.9 MB); the tab
  hides itself when that file is absent.
- **Added** to `scripts/build_population.py` a fixed-tract growth pipeline:
  `load_tracts` plus a generic `interpolate_into` helper areal-interpolate every
  year's block groups (including the PEP-scaled current year) into a single 2020
  tract geography so the yearly panels are comparable; tract geometry is simplified
  and coordinate-rounded to keep the artifact lean. Configurable via
  `EMIT_TRACTS` / `TRACT_GEO_YEAR` / `GROWTH_BASE_YEAR` / `TRACT_SIMPLIFY`.
- **Fixed** the Growth tab rendering — the per-year panels are now inline SVG
  choropleths instead of multiple Leaflet maps, avoiding a hidden-tab sizing bug
  that left the panels blank (only the first card appeared).

## [2.1.0] - 2026-06-03

### Drive-time isochrone map

- **Added** a `2024 (current)` population column: each 2020 block group is aged by
  its county's 2020→2024 Census **PEP** (Population Estimates Program) growth
  factor, then areal-interpolated like any other year — giving a current estimate
  that the decennial/ACS products lag (the fast-growing Williamson County corridor
  was being understated). Configurable via `CURRENT_YEAR`/`PEP_VINTAGE`.
- **Changed** the population table to use honest column labels — ACS 5-year columns
  now read e.g. `2019–23 ACS (~2021)` (a rolling average, not a point-in-time year)
  and the current column reads `2024 (current)`. `population.json` now carries a
  `columns` array and `docs/index.html` renders those labels.
- **Added** `scripts/build_population.py` — for each drive-time band, estimates the
  population living inside it across real US Census years (2010 & 2020 decennial
  100% counts; ACS 5-year for other years, e.g. 2015 & 2023). Reads the band
  polygons from `docs/isochrones.geojson`, pulls Census block-group population and
  TIGER cartographic boundaries for Texas, and areal-interpolates in EPSG:5070
  (`pop = Σ BG_pop × area(BG ∩ band)/area(BG)`). Bands are nested, so each band's
  figure is cumulative (people who can reach the arena within X minutes). Writes
  `docs/population.json`.
- **Added** a population summary-table panel to `docs/index.html` (bands × census
  years + first→last growth %); it degrades gracefully when `population.json` is
  absent.
- **Added** the `Build population` workflow (manual; commits `population.json`,
  which then auto-redeploys via Pages) and the build-time `geopandas`/`shapely`/
  `pyproj` dependencies.
- **Changed** the population build to fetch counties concurrently
  (`CENSUS_WORKERS`) and attribute population with a vectorized intersection
  instead of a per-band overlay, cutting the build from ~15-20 min to a couple of
  minutes.
- **Fixed** the `Build population` commit step so a brand-new (untracked)
  `population.json` is actually committed (`git add` then check `--cached`).

## [1.0.0] - 2026-06-01

First tagged release. Two small, independent components live in this repo.

### Drive-time isochrone map

- **Added** a live drive-time map of the Bell County Expo Center / Cadence Bank
  Arena (301 W Loop 121, Belton, TX), published to GitHub Pages:
  <https://robz-bdb.github.io/Claude-Cloud/>.
- **Added** `scripts/build_isochrones.py` — calls the OpenRouteService isochrones
  API once at build time and writes nested 10/20/30/40/60-minute drive-time bands
  to `docs/isochrones.geojson`, with an approximate concentric-circle fallback
  when `ORS_API_KEY` is unset.
- **Added** a self-contained Leaflet page (`docs/index.html`): color-graded
  bands, arena marker, legend, and fit-to-bounds — no API key needed to view.
- **Added** the `Build isochrones` and `Deploy Pages` workflows; the map
  auto-republishes on pushes to `main` that touch `docs/`.
- Generated the initial real road-network isochrones from OpenRouteService and
  centered the origin on the verified arena coordinates (`31.0305, -97.4787`).

### Notion emoji tagger

- **Added** `scripts/tag_tasks_with_emoji.py` — a daily automation that prepends
  a context-chosen emoji to incomplete, TickTick-synced Notion task titles via a
  single batched Anthropic call. Idempotent (titles already starting with an
  emoji are skipped) with DST-safe 1 AM US-Central scheduling.
- **Added** the `Notion emoji tagger` workflow (scheduled, plus a manual
  dry-run trigger).

[Unreleased]: https://github.com/robz-bdb/Claude-Cloud/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/robz-bdb/Claude-Cloud/compare/v1.0.0...v2.1.0
[1.0.0]: https://github.com/robz-bdb/Claude-Cloud/releases/tag/v1.0.0
