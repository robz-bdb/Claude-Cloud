# CLAUDE.md — <project-name>

Guidance for Claude Code when working on **this project**. This is one project
inside the Claude-Cloud sandbox monorepo; sandbox-wide conventions (layout,
shared tooling, keys) live in the repo-root [`../../CLAUDE.md`](../../CLAUDE.md).
Treat this folder as the working root and don't touch sibling projects.

> Scaffolded from `projects/_template/`. Replace the placeholders below as the
> project takes shape, then delete this note.

## What this project is

<One or two sentences: what it does and why it exists.>

## Commands

```bash
# from this project folder
pip install -r requirements.txt
python src/main.py
```

## Architecture

<The shape of the code: entry points, the main flow, key files.>

## Keys & shared tooling

- Secrets come from the repo-root `.env` (local) or GitHub Actions secrets (CI),
  loaded via `sandbox.env.load_env()` — never hardcode them. See `.env.example`.
- Reusable helpers (env loading, Anthropic/Notion clients) live in `shared/`;
  import them with the bootstrap shown in `src/main.py` and `shared/README.md`.

## Gotchas

<Anything easy to get wrong; non-obvious invariants to preserve.>
