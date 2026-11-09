# Job Market Intelligence & Scoring Pipeline

An end-to-end pipeline that scrapes job postings, structures them with a locally-hosted
LLM, classifies and clusters them with classical ML, scores them against a configurable
fit profile, and publishes a ranked report to Google Sheets — on a schedule, with basic
observability baked in.

Built to demonstrate the full AI/ML engineering lifecycle on one coherent, real dataset:
**scraping → storage → EDA → LLM extraction → classical ML → scoring → automation → deployment.**

---

## Why this project exists

This isn't a toy notebook. It's structured the way a small paid tool would actually be
built and handed off: containerized, configurable, documented, with a schema migration
history and a CI check — so it can run on a laptop today and on a cloud VM tomorrow
without code changes, only config changes.

## Architecture at a glance

```
Scrapers (Playwright + public APIs, async, rate-limited)
   → raw postings → Postgres (JSONB raw + structured columns)
   → EDA (missingness, source balance, text-length, elbow curve for k)
   → LLM extraction (local llama.cpp, grammar-constrained JSON) → fills structured fields
   → Classifier (scikit-learn) → category labels (seniority, remote/onsite, etc.)
   → Clustering (scikit-learn) → market segment groupings
   → Weightage scorer (config-driven, formula → learned) → fit score per posting
   → Google Sheets writer → final ranked report
   → Scheduler + run log → repeatable, observable pipeline
```

Full design rationale: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## Status

This project is being built in phases, tracked in [`docs/PROGRESS.md`](docs/PROGRESS.md).

| Phase | Status |
|---|---|
| 0 — Project scaffold & containerization | ✅ |
| 1 — Environment / config / DB layer | ✅ |
| 2 — Database schema & migrations | ✅ |
| 3 — Scrapers (API + Playwright) | ✅ |
| 4 — EDA | ✅ |
| 5 — LLM extraction (grammar-constrained) | ✅ |
| 6 — Classification & clustering | ✅ |
| 7 — Weightage scoring (v1 formula, v2 learned) | ✅ |
| 8 — Google Sheets reporting | ✅ |
| 9 — Scheduling, observability, deployment | ✅ |

Code is complete and unit-tested (`pytest` — 13/13 passing, pure logic, no
Docker required). **Nothing has been run end-to-end against live Postgres/LLM
yet** — that's the next step, and `docs/RUNBOOK.md` walks through it exactly.

## Quickstart

Full walkthrough: [`docs/RUNBOOK.md`](docs/RUNBOOK.md). Short version:

```bash
cp .env.example .env && cp config/profile.example.yaml config/profile.yaml
# edit both files with your real values
docker compose up -d postgres && docker compose run --rm migrate
docker compose run --rm scraper
docker compose run --rm scraper python -m src.eda.run_eda
# ...then Phase 5 onward — see docs/RUNBOOK.md for the full sequence
docker compose down           # tears everything down cleanly
```

## Evaluation (M2)

The category classifier is evaluated in `docs/RESULTS.md`, which `scripts/evaluate_classifier.py` regenerates; the
numbers below are from 2026-11-09.

- **Data:** 252 English postings in 7 categories. 26 are labelled by hand, 226 by a local LLM (Qwen3.5-9B through
  llama.cpp, `scripts/llm_prelabel.py`). On 18 postings checked against the hand labels the LLM agreed 14 times
  (95% interval 55% to 91%, `docs/LLM_LABEL_CHECK.md`).
- **Method:** repeated stratified group k-fold (5 x 5), TF-IDF fitted inside every fold, near-duplicate postings kept
  in the same fold, plus a shuffled-label control.
- **Result:** logistic regression reaches accuracy 0.60 and macro-F1 0.56, a random forest 0.56 and 0.39, and always
  guessing the most frequent class 0.26 and 0.06. The pipeline therefore uses logistic regression.
- **What this does and does not show:** the scores measure agreement with mostly LLM-made labels, not with the truth.
  The data set is small and comes from one scrape of two job APIs, and roles on the border between categories
  (account managers, product managers, designers) are labelled inconsistently. See the limitations in
  `docs/RESULTS.md`.

## Tech stack

- **Language:** Python 3.11
- **Scraping:** Playwright (async), public job-board APIs
- **Storage:** PostgreSQL 16 (JSONB + structured columns)
- **LLM extraction:** llama.cpp server, grammar-constrained (GBNF) JSON output
- **Classical ML:** scikit-learn (TF-IDF, logistic regression, KMeans)
- **Scoring:** config-driven weighted formula → optional learned Ridge regression
- **Reporting:** Google Sheets (gspread / Apps Script)
- **Orchestration:** Docker Compose (local) → portable to any container host
- **Scheduling:** cron-in-container (local/cloud), Windows Task Scheduler (native fallback)

## Repository layout

```
src/
  scraper/        # async scraper framework + per-source adapters
  database/       # schema, migrations, connection pooling
  eda/            # exploratory data analysis scripts + generated reports
  llm_extraction/ # grammar-constrained LLM field extraction
  ml/             # classifier + clustering
  scoring/        # weightage scorer v1 (formula) and v2 (learned)
  automation/      # Sheets writer, scheduler, run logging
  common/         # shared config loading, logging, db session helpers
config/           # environment-agnostic config (sources, skills, scoring weights)
docs/             # architecture, decisions, runbook, progress log
scripts/          # one-off / operational scripts (migrations, seed data)
tests/            # unit + integration tests
```
