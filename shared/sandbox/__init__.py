"""Shared sandbox tooling.

Small, dependency-light helpers that any project in this monorepo can reuse:
config/env loading (`sandbox.env`) and API client factories (`sandbox.clients`).

Projects make this importable with a 2-line bootstrap that puts the repo root on
`sys.path` — see `shared/README.md` and `projects/_template/src/main.py`.
"""

__all__ = ["env", "clients"]
