# Build Progress Log

Each entry is a real session log — what was built, what decisions were made, what's next.
This doubles as your "how do I explain this project in an interview" cheat sheet later.

---

## Session 0 — Project scaffold & containerization plan
**Date:** 2026-07-24

- Set up repository structure (`src/` split by pipeline stage, `config/`, `docs/`, `tests/`).
- Decided: full containerization from day one (Docker Compose), not native-Windows-first.
  Rationale in `docs/ARCHITECTURE.md` §1.
- Decided: scorer profile (skills, weights, salary floor) lives in `config/profile.yaml`,
  not hardcoded — makes the tool genuinely reusable. Rationale in §4.
- Decided: source adapters pattern for the scraper (`src/scraper/sources/`) instead of a
  monolithic script — one file per job source, shared interface. Rationale in §3.
- Next: Phase 1 — Docker Compose stack (Postgres + app container), `.env` config,
  base `Dockerfile`, dependency management.

---

---

## Session 1 — Full pipeline build, all 9 phases
**Date:** 2026-07-25

Built the complete codebase end to end in one pass, per your request to see the
whole thing before testing/running it yourself:

- **Phase 1** — `src/common/config.py` (two-layer Settings/Profile), `logging.py`
  (structlog), `db.py` (SQLAlchemy session scope), `models.py` (ORM).
- **Phase 2** — Alembic wired to our own Settings; two migrations (`postings`,
  `runs` tables).
- **Phase 3** — Source-adapter pattern; `remoteok.py` + `arbeitnow.py` (API
  sources, no config needed); `generic_playwright.py` (config-driven, async,
  semaphore-bounded scraped source template); orchestrator with dedupe +
  upsert-ignore-duplicates.
- **Phase 4** — `run_eda.py`: missingness report, source-balance chart,
  text-length histogram, KMeans elbow curve with an auto-suggested k.
- **Phase 5** — `schema.gbnf` grammar + `extractor.py` calling llama.cpp's
  native `/completion` endpoint with grammar-constrained sampling; batch
  `main.py`.
- **Phase 6** — TF-IDF features shared by both models; RandomForest classifier
  (with CV, minimum-label-count guard); KMeans clustering with human-readable
  cluster term summaries; `scripts/label_batch.py` interactive labeling CLI.
- **Phase 7** — `formula_scorer.py` (v1, transparent weighted formula) and
  `learned_scorer.py` (v2, Ridge regression on your own hand-ratings, with a
  minimum-rated-count guard); `main.py` auto-switches to v2 once trained.
- **Phase 8** — `sheets_writer.py`: service-account auth, ranked report write,
  `reported_at` tracking.
- **Phase 9** — `scheduler.py` (APScheduler, chains all stages, fail-forward
  per stage) + `run_logger.py` (every stage logs to the `runs` table).
- Wrote 13 pure-logic unit tests (config loader, v1 scorer sub-scores, dedupe)
  and **actually ran them** — all 13 passing, not just syntax-checked.
- Ran `py_compile` across every `.py` file in the repo — confirmed zero syntax
  errors before delivery.

**Honest status:** this is a complete, internally-consistent, tested-at-the-
unit-level codebase. It has **not** been run against real Postgres, a real
llama.cpp server, or real Google Sheets yet — that integration testing is the
next step, and it'll surface the usual first-run issues (a wrong env var, a
missing system lib) that no amount of unit testing catches. `docs/RUNBOOK.md`
is written to walk through exactly that process with a "how do I know it
worked" check at every step.

**Next session:** work through `docs/RUNBOOK.md` together, step by step, fixing
whatever breaks on your actual machine — that's normal and expected, not a
sign anything was built wrong.

<!-- Append new session entries below as we build. Keep them honest — including what
broke and how it was fixed. That history is worth more in an interview than a clean
success story. -->
