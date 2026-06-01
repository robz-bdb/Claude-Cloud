# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/robz-bdb/Claude-Cloud/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/robz-bdb/Claude-Cloud/releases/tag/v1.0.0
