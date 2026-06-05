# Notion task emoji tagger

A daily automation that gives your TickTick-synced Notion tasks a little
personality. Every night it scans the **`tasks-db`** Notion page's inline
**"All Tasks"** database, finds every **incomplete** task (Checkbox unchecked)
whose title doesn't already start with an emoji, asks Claude for a fitting emoji,
and prepends it to the task title:

```
Buy groceries        ->  🛒 Buy groceries
Email the landlord   ->  📧 Email the landlord
Morning run          ->  🏃 Morning run
```

> Because the Notion ↔ TickTick sync is **bidirectional on the title**, the emoji
> also shows up on the task in TickTick.

## How it works

- [`scripts/tag_tasks_with_emoji.py`](scripts/tag_tasks_with_emoji.py) does the
  work: query Notion → filter → ask Claude for emojis (one batched call) →
  prepend to each title. It is idempotent — titles already starting with an
  emoji are skipped, so re-runs never double-tag.
- [`.github/workflows/notion-emoji-tagger.yml`](.github/workflows/notion-emoji-tagger.yml)
  runs it on a schedule. GitHub cron is UTC with no DST handling, so it triggers
  at **06:00 and 07:00 UTC** and the script's `America/Chicago` guard only does
  work when the local hour is 1 — exactly **1 AM US Central** year-round.

## One-time setup

1. **Create a Notion integration** at <https://www.notion.so/my-integrations>
   (internal integration) and copy its token (`ntn_...`).
2. **Share the database with it:** open the `tasks-db` page in Notion →
   **•••** menu → **Connections** → add your integration. This is required —
   the integration can only see pages explicitly shared with it.
3. **Add GitHub repository secrets** (Settings → Secrets and variables →
   Actions → *New repository secret*):
   - `NOTION_TOKEN` — the integration token from step 1
   - `ANTHROPIC_API_KEY` — an Anthropic API key from <https://console.anthropic.com>

That's it. The scheduled run starts working the next night.

## Testing it

Use the manual trigger first — it defaults to a safe **dry run** (logs intended
changes, writes nothing):

- GitHub → **Actions** → *Notion emoji tagger* → **Run workflow** →
  leave *dry_run* checked → **Run**. Inspect the logs.
- Run it again with *dry_run* **unchecked** to apply the changes, then check a
  few tasks in Notion.

### Running locally

```bash
pip install -r requirements.txt

export NOTION_TOKEN="ntn_..."
export ANTHROPIC_API_KEY="sk-ant-..."
export DRY_RUN=1        # log only, no writes
export FORCE_RUN=1      # bypass the 1 AM Central time guard

python scripts/tag_tasks_with_emoji.py
```

## Configuration

All configuration is via environment variables:

| Variable              | Required | Default                              | Purpose |
|-----------------------|----------|--------------------------------------|---------|
| `NOTION_TOKEN`        | yes      | —                                    | Notion integration token |
| `ANTHROPIC_API_KEY`   | yes      | —                                    | Anthropic API key |
| `TASKS_DB_ID`         | no       | `b971e3b6eebb83cc91450191f70d4278`   | The "All Tasks" database ID |
| `TITLE_PROPERTY`      | no       | `Title`                              | Title property name |
| `COMPLETION_PROPERTY` | no       | `Checkbox`                           | Checkbox property marking completion |
| `DRY_RUN`             | no       | `false`                              | Log changes without writing |
| `FORCE_RUN`           | no       | `false`                              | Skip the 1 AM Central time guard |

---

> **Moved:** the drive-time isochrone map and its population/growth layers that used to
> live here now have their own home at
> [`robz-bdb/stampede-hockey-mapping`](https://github.com/robz-bdb/stampede-hockey-mapping)
> (live map: <https://robz-bdb.github.io/stampede-hockey-mapping/>).
