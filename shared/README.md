# `shared/` — tooling reused across sandbox projects

Small, dependency-light helpers so each project doesn't re-implement env loading
and API client wiring. Everything lives under the importable `sandbox` package.

## What's here

| Module | Provides |
|--------|----------|
| `sandbox.env`     | `load_env()` — load a repo-root `.env` into `os.environ` (no-op in CI, never overwrites set vars); `require(name)` — fetch a var or raise a clear error. |
| `sandbox.clients` | `anthropic_client()` — configured `anthropic.Anthropic`; `notion_session()` — a `requests.Session` with Notion auth + version headers. |

## Using it from a project

The `sandbox` package lives at `shared/sandbox/`, so put **`shared/`** on
`sys.path`, then import `sandbox.*`. This bootstrap (also shipped in
`projects/_template/src/main.py`) walks up to find `shared/`, so it works at any
nesting depth:

```python
import sys, pathlib
for _a in pathlib.Path(__file__).resolve().parents:
    if (_a / "shared" / "sandbox").is_dir():
        sys.path.insert(0, str(_a / "shared"))
        break

from sandbox.env import load_env, require
from sandbox.clients import anthropic_client, notion_session

load_env()                      # picks up repo-root .env for local runs
client = anthropic_client()     # uses ANTHROPIC_API_KEY
notion = notion_session()       # uses NOTION_TOKEN
```

Install the deps your project actually uses: `pip install -r shared/requirements.txt`
(or just the subset you need).

## Keys

Secrets are defined **once**, never per project:

- **Local:** a repo-root `.env` (untracked — see `.env.example`). `load_env()`
  reads it.
- **CI:** GitHub Actions repository secrets, passed into the workflow `env:`.

Never hardcode keys in a project or commit a real `.env`.
