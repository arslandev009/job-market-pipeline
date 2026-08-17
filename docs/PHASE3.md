# Phase 3 — Scraping (APIs + Playwright)

## What this phase is, in plain language

"Scraping" covers two very different things people lump together: calling a
public API that already hands you structured JSON (easy, reliable, usually
legally uncomplicated), and parsing HTML from a page that was built for
humans to read, not machines (harder, breaks when the page redesigns, needs
care around a site's terms of service). This project deliberately does both,
so you can point at either skill depending on what a job posting asks for.

## What we built

- **`src/scraper/sources/base.py`** — the shared contract: every source, no
  matter how it works internally, must produce a list of `RawPosting` objects.
- **`remoteok.py` / `arbeitnow.py`** — API-based sources. Straightforward
  `httpx` calls, JSON parsing, done. These are your reliable baseline data.
- **`generic_playwright.py`** — a config-driven template for scraping a real
  page. This is where the actual browser-automation and concurrency skills
  live: it launches headless Chromium, scrapes multiple posting URLs *in
  parallel* but capped by a semaphore (so you're not opening 50 browser tabs
  at once and hammering someone's server), and handles the fact that
  individual pages *will* fail (404, redirect, changed layout) without taking
  down the whole run.
- **`registry.py` + `main.py`** — the orchestrator. Runs every source enabled
  in your `profile.yaml` concurrently (`asyncio.gather`), merges the results,
  removes duplicate postings by URL, and inserts only the new ones into
  Postgres (`ON CONFLICT DO NOTHING`).

## Key concept: async concurrency with a bound

`asyncio.Semaphore(N)` is the standard pattern for "do many things at once,
but never more than N at once." Without it, scraping 100 URLs would try to
open 100 browser pages simultaneously — that's how you get rate-limited,
IP-banned, or just run out of RAM. With it, you get real parallelism (much
faster than one-at-a-time) with a safety ceiling.

## Key concept: fail loudly, skip, keep going

Every source's `fetch()` — and every individual item within it — is wrapped so
one bad response can't crash the entire scrape run. This mirrors how real
ingestion pipelines are built: partial success beats total failure.

## A note on ethics/legality

Before pointing the Playwright adapter at a real site: check its `/robots.txt`
and terms of service. This project ships with the adapter *unconfigured* by
default (no URLs) for exactly that reason — it's your call which site to point
it at once you've checked.
