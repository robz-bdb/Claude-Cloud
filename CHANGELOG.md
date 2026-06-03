# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
