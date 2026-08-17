# Phase 1 — Environment, Config, Database Connection

## What this phase is, in plain language

Every real application needs three foundations before it does anything useful:
a way to configure itself differently on different machines, a way to log what
it's doing, and a reliable connection to its database. Get these three things
right once, and every other phase just builds on top without re-solving them.

## What we built

- **`src/common/config.py`** — reads settings from two places on purpose:
  environment variables (`.env`) for *machine-specific secrets* (DB password,
  API URLs), and `config/profile.yaml` for *your personal preferences* (skills,
  salary floor). Mixing these would mean every time you change your salary
  target you're editing a file full of passwords.
- **`src/common/logging.py`** — structured logging. Instead of scattered
  `print()` statements, every log line is a structured event
  (`scrape_complete fetched=40 inserted=12`) that's easy to search and filter
  later, especially once this runs unattended on a schedule.
- **`src/common/db.py`** — one shared way to open a database connection/session
  for the whole app, with automatic commit-on-success / rollback-on-error.

## Key concept: separation of config from code

Nowhere in this codebase do you hardcode a password, a skill name, or a URL.
That's not paranoia — it's what makes this a *tool* instead of a *script*: the
exact same code runs for anyone who fills in their own `.env` and `profile.yaml`.
