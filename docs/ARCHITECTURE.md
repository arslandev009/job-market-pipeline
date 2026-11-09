# Architecture & Design Decisions

This document exists because a professional handoff explains *why*, not just *what*.
Anyone picking up this repo cold — including you, six months from now — should be able
to read this and understand every structural decision without archaeology.

## 1. Why containerize everything, including local dev?

The original plan (native Windows install of Postgres, venv, native llama.cpp) works,
but it means "how do I run this" has a different answer on every machine. Containerizing
from day one means:

- `docker compose up` is the *only* onboarding instruction that ever needs to exist.
- The exact same Compose file that runs on your desktop is what you'd deploy to a cloud
  VM (DigitalOcean droplet, your own server, etc.) — no "works on my machine" gap.
- Postgres, the app, and (optionally) the LLM server are isolated from your host Python/
  Node setup, so this project can't collide with your other projects (Tools1Hub, Kapture,
  SpecsGiant, etc.) sharing the same machine.

Trade-off: GPU passthrough for the local LLM (RX580, Vulkan) is more fragile inside
Docker on Windows than running llama.cpp natively. We handle this with a **hybrid mode**:
the LLM server can run natively on the host (fast, GPU-accelerated) while everything else
runs in containers and reaches it via `host.docker.internal`. This is documented per-phase
in Phase 5's README, not hidden as a footnote.

## 2. Why Postgres with JSONB, not a pure relational schema or a document DB?

Job postings are semi-structured: some fields (title, company, URL) are always present
and queryable; others (extracted skills, salary range) are filled in later, by a
probabilistic process (the LLM), and may legitimately fail to extract. JSONB gives us:

- A durable `raw_html`/`raw_payload` column that preserves the original scrape — if the
  extraction schema changes later, we can re-run extraction without re-scraping.
- Structured, indexed, queryable columns for everything the rest of the pipeline depends
  on (dedupe key, timestamps, scores).

This is the same reasoning a production ingestion pipeline uses: **store what you scraped
verbatim, derive everything else, and make derivation replayable.**

## 3. Why source adapters instead of one big scraper script?

`src/scraper/sources/` holds one small module per source, each implementing the same
interface (`fetch(config) -> list[RawPosting]`). This is the standard "adapter pattern"
for ingestion pipelines: adding a new job board later means adding one file, not editing
a monolith. It also isolates breakage — when a site changes its HTML (it will), only one
adapter needs fixing, and the async orchestrator already fails loudly-and-skips per source
rather than crashing the whole run.

## 4. Why config-driven skills/weights instead of hardcoded?

The scorer's "my skills" list and weighting formula are the part of this tool that's
*personal* — different for every user, and likely to change over time. Hardcoding them
means the tool only ever works for one person's one job search. Pulling them into
`config/profile.yaml` means:

- The same codebase is a genuinely reusable tool, not a portfolio one-off.
- Config changes (new skill, different salary floor) don't require touching Python or
  redeploying — a real separation of concerns between "the tool" and "your data."

## 5. Why grammar-constrained LLM extraction instead of prompting for JSON and parsing?

Free-form JSON generation from a local 7B-class model fails often enough (trailing
commas, extra prose, wrong enum casing) that naive `json.loads()` on the output is
unreliable in practice. GBNF grammar constraining forces the model's token sampling to
only ever produce grammatically valid JSON matching our schema — it moves validation from
"catch it after the fact" to "make it structurally impossible to fail." This is a real
technique used in production structured-extraction pipelines, not a toy trick.

## 6. Why classical ML (TF-IDF + logistic regression/KMeans) instead of another LLM pass?

Two reasons, both deliberate:

1. **Cost/latency** — classifying and clustering thousands of postings with an LLM call
   per posting is slow and wasteful when a sub-second classical model does the job.
2. **JD alignment** — the target role explicitly wants classical ML skills (scikit-learn,
   feature engineering, clustering) demonstrated alongside LLM skills, not LLM-for-everything.

## 7. Why a two-stage scorer (formula → learned)?

A hardcoded weighted formula is transparent, debuggable, and ships in an afternoon — it's
the right v1. But "0.5 skill match + 0.3 salary fit + 0.2 location fit" is a guess at your
own preferences. v2 replaces the guess with a small regression model trained on your own
hand-ratings, which is a genuine (if small) example of going from a heuristic to a learned
system — the exact kind of maturity curve real internal tools follow.

## 8. Deployment target

Local-first, cloud-optional. The Compose stack is written to run identically on:
- A Windows machine via Docker Desktop (dev/demo).
- Any Linux VM/VPS via `docker compose up -d` (persistent, scheduled operation).
- Container orchestration platforms later, if needed (the services are already 12-factor:
  config via env vars, no local state outside the named Postgres volume).

No cloud-specific code is written anywhere in `src/` — deployment is a Compose/environment
concern, not an application concern.
