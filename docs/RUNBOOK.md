# Runbook — Bring the whole pipeline up, step by step

Follow this top to bottom the first time. Every step tells you what should happen
and how to tell if it worked, so you're never guessing.

## 0. Prerequisites

- Docker Desktop installed and running (WSL2 backend on Windows is fine, not required).
- (Optional, for Phase 5) `llama-server.exe` from llama.cpp, built with Vulkan support
  for your RX580, with a GGUF model downloaded (e.g. a 7B instruct model, Q4_K_M quant).
- (Optional, for Phase 8) A Google Cloud service account with Sheets + Drive API enabled.

## 1. Configure

```bash
cp .env.example .env
cp config/profile.example.yaml config/profile.yaml
```

Edit `.env` — at minimum, change `POSTGRES_PASSWORD` to something real.
Edit `config/profile.yaml` — put in your actual skills, salary floor, preferred location.

## 2. Bring up the database and run migrations

```bash
docker compose up -d postgres
docker compose run --rm migrate
```

**Check it worked:**
```bash
docker compose exec postgres psql -U jmp_user -d job_market -c "\dt"
```
You should see `postings` and `runs` tables listed.

## 3. Run the scraper

```bash
docker compose run --rm scraper
```

This hits RemoteOK and Arbeitnow's public APIs (no config needed) and inserts new
postings. **Check it worked:**
```bash
docker compose exec postgres psql -U jmp_user -d job_market -c "SELECT count(*), source FROM postings GROUP BY source;"
```

If you want the scraped (Playwright) source too: copy
`config/scrape_targets.example.yaml` to `config/scrape_targets.yaml`, fill in real
URLs/selectors for a site whose robots.txt allows it, then re-run the scraper.

## 4. Run EDA

```bash
docker compose run --rm scraper python -m src.eda.run_eda
```

Look at the printed summary in your terminal, and open the generated plots in
`docs/eda_report/`. Note the "Suggested cluster count (k)" — you'll use that
number in Phase 6.

## 5. Set up the local LLM (Phase 5)

This runs **natively on your host**, not in Docker (GPU passthrough reasons — see
`docs/ARCHITECTURE.md` §1):

```bash
llama-server.exe -m path\to\your-model.gguf --port 8080
```

Leave that running in its own terminal. Then:

```bash
docker compose run --rm extractor
```

**Check it worked:**
```bash
docker compose exec postgres psql -U jmp_user -d job_market -c "SELECT title, seniority, remote_or_onsite, salary_min, salary_max FROM postings WHERE extracted_at IS NOT NULL LIMIT 5;"
```

If `LLM_BASE_URL` can't be reached from inside the container, confirm
`host.docker.internal` resolves — the compose file already adds the necessary
`extra_hosts` entry for Linux; on Windows/Mac Docker Desktop it works out of the box.

## 6. Label some postings by hand (bootstraps ML)

```bash
docker compose run --rm scraper python -m scripts.label_batch --n 30
```

This is interactive — it'll show you postings one at a time in your terminal.
Give each a category (frontend/backend/fullstack/data-ml/devops/other — your
call) and optionally a 1-5 fit rating. Do at least 20-30 for the classifier,
15+ with ratings for the v2 learned scorer later.

## 7. Run classification + clustering

```bash
docker compose run --rm ml
```

First run: clustering happens (unsupervised, no labels needed). Classification
is skipped with a warning until you've labeled enough (step 6). To actually
train the classifier on what you labeled, open a Python shell in the container
and call `train_classifier` — or just re-run `python -m scripts.label_batch`
until you cross the threshold, then edit `src/ml/main.py` temporarily to call
`train_classifier(labeled_df)` once (this manual trigger is intentional — you
don't want an unattended scheduler silently retraining on noisy labels).

## 8. Run scoring

```bash
docker compose run --rm scorer
```

v1 (the formula) runs immediately — no setup needed. **Check it:**
```bash
docker compose exec postgres psql -U jmp_user -d job_market -c "SELECT title, fit_score FROM postings ORDER BY fit_score DESC LIMIT 10;"
```

Once you've rated 15+ postings (step 6), train v2: same pattern as the
classifier — call `train_learned_scorer` once with your rated postings, and
future scoring runs will use it automatically.

## 9. Set up Google Sheets reporting (optional)

Follow `docs/PHASE8.md` to create a service account and get `credentials.json`
into the repo root, then:

```bash
docker compose run --rm sheets-writer
```

## 10. Run everything automatically on a schedule

```bash
docker compose --profile scheduled up -d scheduler
```

This runs the full pipeline immediately, then again every
`sources.scrape_interval_hours` (from `config/profile.yaml`). Check progress:

```bash
docker compose logs -f scheduler
docker compose exec postgres psql -U jmp_user -d job_market -c "SELECT stage, status, started_at, rows_processed FROM runs ORDER BY started_at DESC LIMIT 10;"
```

## 11. Run the test suite

```bash
pip install -r requirements.txt
pytest -v
```
(Tests are pure-logic and don't need Docker/Postgres running.)

## Tear down

```bash
docker compose down        # stop everything, keep data
docker compose down -v     # stop everything AND delete the Postgres volume
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `migrate` fails to connect | Postgres not healthy yet — check `docker compose ps`, wait for healthcheck |
| Scraper inserts 0 rows on 2nd+ run | Correct — `ON CONFLICT DO NOTHING` on URL means it's not re-inserting duplicates |
| Extractor logs `llm_call_failed` | `llama-server.exe` isn't running, or `LLM_BASE_URL` in `.env` is wrong |
| Extractor logs `llm_output_not_valid_json` | Should basically never happen given the grammar — if it does, check your llama.cpp version supports the `grammar` field on `/completion` |
| Classifier always skipped | You haven't labeled `MIN_LABELED_EXAMPLES` (20) postings yet — run step 6 more |
| Sheets writer raises auth error | `credentials.json` missing/invalid, or the sheet isn't shared with the service account email |
