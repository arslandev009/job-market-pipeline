# Phase 5 — LLM Extraction (Grammar-Constrained JSON)

## What this phase is, in plain language

We have messy free-text job postings and we want clean, structured fields out
of them: is this senior or junior, remote or onsite, what's the salary range,
what skills does it actually require. An LLM is good at reading messy text and
understanding it — but by default, LLMs generate free-form text, and asking
one to "please respond in JSON" doesn't *guarantee* valid JSON back. This
phase solves that reliability problem.

## What we built

- **`schema.gbnf`** — a formal grammar (GBNF format, used by llama.cpp) that
  defines exactly what shapes of JSON are legal: which fields, which enums,
  what types. This isn't a validation check run *after* generation — it
  constrains the model's token-by-token sampling *during* generation, so it is
  structurally impossible for the model to output invalid JSON.
- **`extractor.py`** — sends each posting's text to your local llama.cpp
  server's `/completion` endpoint along with the grammar, gets back guaranteed-
  valid JSON, and parses it into an `ExtractionResult`.
- **`main.py`** — batch-processes every posting that hasn't been extracted yet,
  writing results back to the database.

## Key concept: grammar-constrained decoding

Normally, at each step, an LLM picks the next token from a probability
distribution over its whole vocabulary. Grammar constraining masks that
distribution down to *only the tokens that are still grammatically valid*
given what's been generated so far and the grammar rules. The model can still
be *wrong* about the content (it might misjudge seniority), but it literally
cannot produce malformed output — no missing commas, no explanatory prose
before the JSON, no wrong data types.

## Key concept: why local, not a cloud LLM API

This runs against your own RX580 via llama.cpp — no per-request API cost, no
rate limits, and no sending potentially large volumes of scraped text to a
third party. The trade-off is generation is slower and the model is smaller
(so extraction quality is good-not-great compared to a frontier model) — an
honest trade to name in an interview, not hide.

## Key concept: retry the network call, not the parsing

Notice `extractor.py` retries the HTTP call (via `tenacity`) but does *not*
retry-until-valid-JSON — because the grammar already guarantees valid JSON on
any successful response. Retrying belongs where failure can actually happen
(the network), not where it structurally can't (the parsing).
