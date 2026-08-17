# Phase 2 — Database Schema & Migrations

## What this phase is, in plain language

Before you can store anything, you need to decide the shape of your data — and
you need a way to change that shape later *without* deleting everything and
starting over. That's what a migration tool does: it's version control for
your database structure.

## What we built

- **`src/common/models.py`** — the Python-side definition of our two tables
  (`Posting`, `PipelineRun`), used everywhere else in the app to read/write data
  without writing raw SQL by hand.
- **`migrations/versions/0001_initial_schema.py`** — creates the `postings`
  table with every column the *entire pipeline* will eventually fill in: raw
  scrape fields now, LLM-extracted fields later, ML fields later still, score
  and report-status fields last. One table, filled in progressively as data
  flows through each phase — this is intentional (see `docs/ARCHITECTURE.md` §2).
- **`migrations/versions/0002_runs_table.py`** — a second table purely for
  observability: one row per pipeline-stage execution, so you can always answer
  "did last night's scrape actually run, and did it work?"

## Key concept: migrations, not manual schema edits

If you ever need a new column, you write a new migration file (`alembic revision`)
rather than editing the table directly in psql. This means the schema's entire
history is in git, reproducible on any fresh database with one command
(`alembic upgrade head`), and reversible (`downgrade()` on every migration).

## Key concept: JSONB + structured columns together

`raw_payload` (JSONB) keeps the *entire original scrape*, untouched, forever.
Every other column is a structured value *derived* from that raw data by a
later phase. If Phase 5's extraction logic improves later, you can re-run it
against the same `raw_payload` without re-scraping anything.
