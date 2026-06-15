# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repository.

## What this repo is

A **pop-in Claude Code sandbox**: a monorepo of small, independent projects. Each
lives in its own folder under `projects/<name>/` and is self-contained — its own
code, `README.md`, `CLAUDE.md`, and dependencies. Projects do not depend on each
other; the only thing they share is the tooling and keys in `shared/`.

The working model is **one context window ≈ one project**. A fresh session is
assumed to be a *new* project unless it's clearly scoped to an existing one. Work
on different projects happens in different context windows, so each session stays
focused on a single project folder.

```
projects/
  _template/            scaffold copied when starting a new project
  notion-emoji-tagger/  daily Notion task emoji tagger (has its own CLAUDE.md)
shared/                 reusable helpers (sandbox.*) + shared deps; see shared/README.md
.env.example            the shared keys; copy to .env for local runs
```

## Starting work in a session

**First, figure out the scope:**

1. **If the user names or clearly points at an existing project** (e.g. mentions
   `notion-emoji-tagger`, or the task obviously continues it): treat
   `projects/<name>/` as the working root and **defer to that project's own
   `CLAUDE.md`**. Stay inside that folder.

2. **If the session is fresh and not scoped to an existing project**, treat it as
   a **new project**:
   - Ask the user for a short **kebab-case name** and a one-line **intent**.
   - Scaffold it: `cp -r projects/_template projects/<name>` (then fill in the
     placeholders in its `CLAUDE.md` / `README.md`).
   - Work **only** inside `projects/<name>/`.

   Don't scaffold a folder before you have a name — avoid leaving empty/junk
   project dirs.

**In all cases: do not modify sibling projects.** A change for one project stays
within its folder (plus `shared/` only when a shared helper genuinely needs to
change for everyone).

## Shared tools & keys

- **Tools:** `shared/` holds the importable `sandbox` package — `sandbox.env`
  (`load_env()`, `require()`) and `sandbox.clients` (`anthropic_client()`,
  `notion_session()`). Import it with the `sys.path` bootstrap (it walks up to
  `shared/`) documented in `shared/README.md` and shown in
  `projects/_template/src/main.py`.
- **Keys:** defined **once**, never per project. Local runs read a repo-root
  `.env` (git-ignored; template in `.env.example`) via `load_env()`. CI reads
  GitHub Actions repository secrets. Current shared keys: `NOTION_TOKEN`,
  `ANTHROPIC_API_KEY`. **Never hardcode a secret or commit a real `.env`.**

## Conventions & guardrails

- Keep each project self-contained under its folder; reach for `shared/` instead
  of copying helper code between projects.
- Each project owns its own `requirements.txt`; install `shared/requirements.txt`
  too if the project uses the shared client factories.
- Workflows live in `.github/workflows/` at the repo root (GitHub requires that),
  but each scopes itself to its project — e.g. `notion-emoji-tagger.yml` sets
  `working-directory: projects/notion-emoji-tagger`. Match that pattern when a new
  project needs CI, and keep workflow names/paths project-prefixed.
- Update `CHANGELOG.md` when you add a project or make a notable change.

## Projects

| Project | What it is |
|---------|-----------|
| [`notion-emoji-tagger`](projects/notion-emoji-tagger/CLAUDE.md) | Scheduled automation that tags incomplete TickTick-synced Notion tasks with a contextually-chosen emoji, once daily at 1 AM US Central. |
