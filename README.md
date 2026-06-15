# Claude-Cloud

A **pop-in Claude Code sandbox** — a monorepo of small, independent projects.
Each project lives in its own folder under [`projects/`](projects/) with its own
code, docs, and dependencies. The only thing projects share is the tooling and
keys in [`shared/`](shared/).

The idea: **one context window ≈ one project**. Pop into a fresh Claude Code
session aimed at this repo and it's assumed to be a *new* project; keep working
existing projects in their own sessions.

## Layout

```
projects/
  _template/            scaffold for a new project
  notion-emoji-tagger/  daily Notion task emoji tagger
shared/                 reusable helpers (the `sandbox` package) + shared deps
.env.example            shared keys; copy to .env for local runs
CLAUDE.md               sandbox conventions for Claude Code
```

## Start a new project

```bash
cp -r projects/_template projects/<your-kebab-case-name>
# fill in its CLAUDE.md / README.md, then build in projects/<name>/src/
```

New projects get the shared tooling wired up for free — see the bootstrap import
in `projects/_template/src/main.py`.

## Shared tooling & keys

- **Tooling:** [`shared/`](shared/README.md) exposes the importable `sandbox`
  package — env loading (`sandbox.env`) and API client factories
  (`sandbox.clients` → Anthropic, Notion). Any project can import it.
- **Keys:** defined once, never per project. For local runs, copy `.env.example`
  to `.env` (git-ignored) and fill it in; `sandbox.env.load_env()` reads it. In
  CI, the same values come from GitHub Actions repository secrets. Current shared
  keys: `NOTION_TOKEN`, `ANTHROPIC_API_KEY`.

## Projects

- **[notion-emoji-tagger](projects/notion-emoji-tagger/README.md)** — a daily
  automation that prepends a contextually-chosen emoji to incomplete,
  TickTick-synced Notion task titles via a single batched Anthropic call.
  Idempotent, DST-safe 1 AM US-Central schedule.

---

> **Moved:** the drive-time isochrone map that used to live here now has its own
> home at
> [`robz-bdb/stampede-hockey-mapping`](https://github.com/robz-bdb/stampede-hockey-mapping)
> (live map: <https://robz-bdb.github.io/stampede-hockey-mapping/>).
