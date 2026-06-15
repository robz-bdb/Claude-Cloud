#!/usr/bin/env python3
"""Prepend a contextually-chosen emoji to incomplete Notion tasks.

Scans the TickTick-synced "All Tasks" database, finds incomplete tasks
(Checkbox unchecked) whose title does not already start with an emoji, asks
Claude for a fitting emoji per task in one batched call, and prepends it to the
task's Title (e.g. "Buy groceries" -> "🛒 Buy groceries").

Designed to run unattended (daily GitHub Actions cron at 1 AM US Central).
Configured entirely via environment variables; see README.md.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests

# Bootstrap: locate the sandbox `shared/` dir so the shared `sandbox` package is
# importable, then reuse its env loading and Notion/Anthropic client factories.
for _ancestor in pathlib.Path(__file__).resolve().parents:
    if (_ancestor / "shared" / "sandbox").is_dir():
        sys.path.insert(0, str(_ancestor / "shared"))
        break

from sandbox.clients import NOTION_API, anthropic_client, notion_session  # noqa: E402
from sandbox.env import load_env, require  # noqa: E402

# --- Configuration (env) ----------------------------------------------------

# The inline "All Tasks" database inside the `tasks-db` page.
TASKS_DB_ID = os.environ.get("TASKS_DB_ID", "b971e3b6eebb83cc91450191f70d4278")
TITLE_PROPERTY = os.environ.get("TITLE_PROPERTY", "Title")
COMPLETION_PROPERTY = os.environ.get("COMPLETION_PROPERTY", "Checkbox")
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
# Skip the 1-AM-Central guard (set by manual workflow_dispatch runs).
FORCE_RUN = os.environ.get("FORCE_RUN", "").lower() in ("1", "true", "yes")

ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_EMOJI = "📌"
LOCAL_TZ = ZoneInfo("America/Chicago")

# Matches a leading emoji / pictograph (incl. variation selectors and common
# symbol ranges) so we can detect titles that are already tagged.
_EMOJI_PATTERN = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F02F"
    "\U0001F900-\U0001F9FF\U00002190-\U000021FF\U00002B00-\U00002BFF"
    "\U0000FE00-\U0000FE0F\U00002700-\U000027BF\U000024C2\U0000203C"
    "\U00002049\U0001F1E6-\U0001F1FF]"
)


def log(msg: str) -> None:
    print(msg, flush=True)


def fail(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    log(f"ERROR: {msg}")
    sys.exit(1)


# --- Emoji helpers -----------------------------------------------------------

def starts_with_emoji(text: str) -> bool:
    stripped = text.lstrip()
    return bool(stripped) and bool(_EMOJI_PATTERN.match(stripped))


def is_valid_single_emoji(candidate: str) -> bool:
    """Lenient check: a short, non-ASCII token that begins with an emoji."""
    c = candidate.strip()
    if not c or len(c) > 8:
        return False
    if any(ch.isascii() and (ch.isalnum() or ch.isspace()) for ch in c):
        return False
    return bool(_EMOJI_PATTERN.match(c))


# --- Notion ------------------------------------------------------------------

def fetch_incomplete_tasks(session: requests.Session) -> list[dict[str, Any]]:
    """Return all pages where the completion checkbox is unchecked."""
    url = f"{NOTION_API}/databases/{TASKS_DB_ID}/query"
    payload: dict[str, Any] = {
        "filter": {"property": COMPLETION_PROPERTY, "checkbox": {"equals": False}},
        "page_size": 100,
    }
    pages: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        if cursor:
            payload["start_cursor"] = cursor
        resp = session.post(url, json=payload, timeout=30)
        if resp.status_code != 200:
            fail(f"Notion query failed ({resp.status_code}): {resp.text}")
        data = resp.json()
        pages.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return pages


def get_title(page: dict[str, Any]) -> str:
    prop = page.get("properties", {}).get(TITLE_PROPERTY, {})
    return "".join(rt.get("plain_text", "") for rt in prop.get("title", []))


def update_title(session: requests.Session, page_id: str, new_title: str) -> None:
    url = f"{NOTION_API}/pages/{page_id}"
    payload = {
        "properties": {
            TITLE_PROPERTY: {"title": [{"text": {"content": new_title}}]}
        }
    }
    resp = session.patch(url, json=payload, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"{resp.status_code}: {resp.text}")


# --- Emoji selection (Claude) ------------------------------------------------

def choose_emojis(titles: list[str]) -> list[str]:
    """Return one emoji per title (same order), via a single batched call."""
    client = anthropic_client()
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles))
    system = (
        "You assign a single, fitting emoji to each to-do task title. "
        "Reply with ONLY a JSON array of strings, one emoji per task, in the "
        "same order as the input. Each element must be exactly one emoji and "
        "nothing else. No prose, no numbering, no markdown."
    )
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1024,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": f"Tasks:\n{numbered}"}],
    )
    raw = "".join(block.text for block in message.content if block.type == "text").strip()
    # Tolerate accidental code fences.
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log(f"WARNING: could not parse model output, using default emoji.\n{raw}")
        return [DEFAULT_EMOJI] * len(titles)

    emojis: list[str] = []
    for i in range(len(titles)):
        candidate = parsed[i] if i < len(parsed) and isinstance(parsed[i], str) else ""
        emojis.append(candidate.strip() if is_valid_single_emoji(candidate) else DEFAULT_EMOJI)
    return emojis


# --- Main --------------------------------------------------------------------

def within_run_window() -> bool:
    now_local = datetime.now(LOCAL_TZ)
    log(f"Local time (America/Chicago): {now_local:%Y-%m-%d %H:%M %Z}")
    return now_local.hour == 1


def main() -> None:
    load_env()  # pick up a repo-root .env for local runs (no-op in CI)
    try:
        notion = notion_session()      # requires NOTION_TOKEN
        require("ANTHROPIC_API_KEY")   # fail fast before doing any Notion work
    except RuntimeError as exc:
        fail(str(exc))

    if not FORCE_RUN and not within_run_window():
        log("Outside the 1 AM Central run window; exiting (set FORCE_RUN=1 to override).")
        return

    pages = fetch_incomplete_tasks(notion)
    log(f"Scanned {len(pages)} incomplete task(s).")

    eligible: list[tuple[str, str]] = []  # (page_id, title)
    for page in pages:
        title = get_title(page)
        if not title.strip():
            continue
        if starts_with_emoji(title):
            continue
        eligible.append((page["id"], title))

    if not eligible:
        log("No eligible tasks (all complete, empty, or already emoji-tagged).")
        return

    log(f"{len(eligible)} task(s) need an emoji.")
    emojis = choose_emojis([t for _, t in eligible])

    updated = failed = 0
    for (page_id, title), emoji in zip(eligible, emojis):
        new_title = f"{emoji} {title}"
        if DRY_RUN:
            log(f"[dry-run] {title!r} -> {new_title!r}")
            continue
        try:
            update_title(notion, page_id, new_title)
            log(f"updated: {new_title!r}")
            updated += 1
            time.sleep(0.34)  # stay under Notion's ~3 req/s limit
        except Exception as exc:  # noqa: BLE001 - keep going on per-page errors
            log(f"FAILED to update {title!r}: {exc}")
            failed += 1

    log(
        f"Done. scanned={len(pages)} eligible={len(eligible)} "
        f"updated={updated} failed={failed} dry_run={DRY_RUN}"
    )


if __name__ == "__main__":
    main()
