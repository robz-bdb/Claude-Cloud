"""Environment / secret loading shared across sandbox projects.

Keys live in ONE place: a repo-root `.env` for local runs (untracked; see
`.env.example`) or GitHub Actions secrets in CI. `load_env()` makes the local
`.env` available without adding a dependency; CI sets real env vars directly, so
calling `load_env()` there is a harmless no-op (it never overwrites a var that
is already set).
"""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """Repo root = two levels up from this file (shared/sandbox/env.py)."""
    return Path(__file__).resolve().parents[2]


def load_env(path: str | os.PathLike[str] | None = None) -> None:
    """Load `KEY=VALUE` lines from a `.env` file into `os.environ`.

    - Defaults to the repo-root `.env`; silently does nothing if it's absent.
    - Skips blank lines and `#` comments; strips an optional `export ` prefix and
      surrounding quotes on the value.
    - Never overwrites a variable that is already set (CI / real env wins).
    """
    env_path = Path(path) if path is not None else repo_root() / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def require(name: str) -> str:
    """Return env var `name`, or raise a clear error naming it."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Required environment variable {name!r} is not set. "
            f"Add it to a repo-root .env (see .env.example) or your CI secrets."
        )
    return value
