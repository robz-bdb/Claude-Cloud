"""API client factories shared across sandbox projects.

Thin wrappers so individual projects don't re-derive auth headers / key wiring.
Imports of the third-party SDKs are deferred into each factory so a project that
doesn't need a given client doesn't have to install its dependency.
"""

from __future__ import annotations

from typing import Any

from .env import require

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def anthropic_client(api_key: str | None = None) -> Any:
    """Return a configured `anthropic.Anthropic` client.

    Uses `ANTHROPIC_API_KEY` from the environment unless `api_key` is passed.
    Requires the `anthropic` package (see `shared/requirements.txt`).
    """
    from anthropic import Anthropic

    return Anthropic(api_key=api_key or require("ANTHROPIC_API_KEY"))


def notion_session(token: str | None = None) -> Any:
    """Return a `requests.Session` pre-configured for the Notion REST API.

    Sets the bearer auth, `Notion-Version`, and JSON content-type headers so
    callers can just `session.post(f"{NOTION_API}/...", json=...)`. Uses
    `NOTION_TOKEN` from the environment unless `token` is passed. Requires the
    `requests` package (see `shared/requirements.txt`).
    """
    import requests

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token or require('NOTION_TOKEN')}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }
    )
    return session
