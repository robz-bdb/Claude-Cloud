#!/usr/bin/env python3
"""Entry point for <project-name>.

Starter that wires up the sandbox shared tooling. Delete what you don't need.
"""

from __future__ import annotations

import pathlib
import sys

# Bootstrap: walk up to the sandbox `shared/` dir and put it on sys.path so the
# shared `sandbox` package is importable from anywhere in the repo.
for _ancestor in pathlib.Path(__file__).resolve().parents:
    if (_ancestor / "shared" / "sandbox").is_dir():
        sys.path.insert(0, str(_ancestor / "shared"))
        break

from sandbox.env import load_env  # noqa: E402


def main() -> None:
    load_env()  # picks up the repo-root .env for local runs (no-op in CI)
    # from sandbox.clients import anthropic_client, notion_session
    # client = anthropic_client()
    print("hello from <project-name>")


if __name__ == "__main__":
    main()
