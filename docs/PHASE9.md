# Phase 9 — Scheduling, Observability & Deployment

## What this phase is, in plain language

A pipeline you have to remember to run by hand isn't a pipeline, it's a chore.
This phase turns every previous phase into one automated, observable, and
deployable system.

## What we built

- **`src/automation/scheduler.py`** — a long-running process (APScheduler)
  that chains every stage (scrape → extract → ml → score → report) in order,
  on an interval you set in `profile.yaml`, and runs once immediately on
  startup so you're not waiting a full day for first output.
- **`src/automation/run_logger.py`** — every single stage, whether run
  manually or by the scheduler, writes a row to the `runs` table on start and
  updates it with status/row-count/error on finish. This is "basic
  observability": you can always answer "did last night's run work?" with one
  SQL query, without digging through logs.
- **`docker-compose.yml`** — Compose *profiles* let one file serve multiple
  purposes: `docker compose up postgres` for just the DB, `docker compose run
  --rm <service>` to run any single stage manually, and `docker compose
  --profile scheduled up -d scheduler` to run the whole thing as a persistent
  background daemon — locally or on any cloud VM, identically.

## Key concept: fail-forward pipeline sequencing

The scheduler catches exceptions *per stage*, logs them, and moves to the next
stage rather than aborting the whole run. If extraction fails but scraping
succeeded, you still want that new raw data sitting in the database for
tomorrow's run to pick up — not lost because one downstream stage choked.

## Key concept: deployment is a config concern, not a code concern

Nothing in `src/` knows or cares whether it's running on your Windows desktop
or a $5/month Linux VPS. The only things that differ between "local" and
"cloud" are environment variables (`.env`) and which Compose profile you
activate. This is the practical meaning of "12-factor app" design, and it's
why this project can be a genuine portfolio piece — it's provably not
hardcoded to one machine.

## Deploying to an actual cloud server (optional, once local works)

1. Provision any Linux VM (DigitalOcean, Hetzner, your own server at a fixed
   IP, etc.) with Docker + Docker Compose installed.
2. `git clone` this repo onto it (or `scp` the folder over).
3. Repeat the Runbook from step 1 — same `.env`/`profile.yaml` setup, same
   commands. The only real difference: Phase 5's LLM either needs to also run
   on that box (if it has a GPU) or you point `LLM_BASE_URL` at wherever it's
   reachable — including your own desktop machine, if the VM can reach it.
4. `docker compose --profile scheduled up -d scheduler` and it runs
   unattended, restarting automatically on VM reboot (`restart:
   unless-stopped` is already set in the compose file).
