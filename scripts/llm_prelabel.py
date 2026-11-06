"""LLM pre-labelling of the not-yet-labelled English postings (M2.4).

Why: hand-labelling all ~250 postings is slow. This script asks the local llama.cpp server (the same
one the extractor uses) to pick ONE of the 7 categories for every English posting that has no label yet.

These are SILVER labels, not gold: they are saved with category_label_source = 'llm' so nothing that
trains or evaluates on hand labels ('manual') ever mixes them in by accident. Every prediction is also
appended to data/processed/llm_labels.csv so a later human audit can measure how often the LLM was wrong.

Run (needs the llama.cpp server up; the data folder must be mounted so the CSV survives the container):
    docker compose run --rm --no-deps extractor python -m scripts.llm_prelabel --dry --limit 10
    docker compose run --rm --no-deps -v "<repo>/data:/app/data" extractor python -m scripts.llm_prelabel
"""
from __future__ import annotations

import argparse
import csv
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select

from scripts.label_batch import CATEGORIES
from src.common.db import session_scope
from src.common.language import is_english
from src.common.logging import configure_logging
from src.common.models import Posting
from src.common.text_clean import clean_html_text

CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "processed" / "llm_labels.csv"
MAX_TEXT_CHARS = 1500
MAX_CONSECUTIVE_ERRORS = 5

GRAMMAR = "root ::= " + " | ".join(f'"{c}"' for c in CATEGORIES)

SYSTEM = "You classify job postings into exactly one category. Reply with the category name only."

DEFINITIONS = """Categories:
- software_engineering: writes, builds or tests software (backend, frontend, mobile, QA, engineering managers).
- data_ai_ml: data science, data engineering, analytics, machine learning, AI engineering or research.
- devops_cloud_security: infrastructure, cloud architecture, DevOps/SRE, IT systems, cyber security.
- sales_marketing: sales, account executives, business development, marketing, growth.
- customer_support_admin: customer support or success, scheduling, virtual assistants, coordinators, administrative and data-entry roles.
- management_finance_hr: non-technical management, accounting, finance, tax, HR, recruiting, legal, operations.
- other: anything else (healthcare, science, trades, education, ...) or unclear.
Decide by the main duties of the job, not by the company's industry.

Examples (title -> category):
Senior Software Engineer -> software_engineering
AI ML Engineer -> data_ai_ml
AWS Cloud Solutions Architect -> devops_cloud_security
Account Executive -> sales_marketing
Virtual Scheduling Assistant -> customer_support_admin
Senior Property Manager -> management_finance_hr
Clinical Data Manager -> other
"""


def build_prompt(title: str, company: str, text: str) -> str:
    user = f"{DEFINITIONS}\nJob posting:\nTitle: {title}\nCompany: {company}\nText: {text[:MAX_TEXT_CHARS]}\n\nCategory:"
    return (f"<|im_start|>system\n{SYSTEM}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n"
            "<|im_start|>assistant\n")


def completion_url(base: str) -> str:
    base = base.rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base + "/completion"


def ask_llm(client: httpx.Client, url: str, prompt: str) -> tuple[str, str]:
    payload = {"prompt": prompt, "n_predict": 16, "temperature": 0, "grammar": GRAMMAR,
               "cache_prompt": True, "stream": False}
    r = client.post(url, json=payload)
    r.raise_for_status()
    data = r.json()
    label = (data.get("content") or "").strip()
    if label not in CATEGORIES:
        raise ValueError(f"model returned an unexpected label: {label!r}")
    return label, str(data.get("model") or "")


def load_candidates(limit: int | None) -> list[tuple[int, str, str, str]]:
    out: list[tuple[int, str, str, str]] = []
    with session_scope() as session:
        rows = session.scalars(
            select(Posting).where(Posting.category_label_source.is_(None)).order_by(Posting.id)).all()
        for p in rows:
            text = clean_html_text(p.raw_text)
            if is_english(text):
                out.append((p.id, p.title or "", p.company or "", text))
            if limit and len(out) >= limit:
                break
    return out


def save_label(posting_id: int, label: str) -> bool:
    """Only ever fills an UNLABELLED posting; hand labels are never overwritten."""
    with session_scope() as session:
        p = session.get(Posting, posting_id)
        if p is None or p.category_label_source is not None:
            return False
        p.category_label = label
        p.category_label_source = "llm"
        return True


def append_csv(rows: list[dict]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    new = not CSV_PATH.exists()
    with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "llm_label", "model", "labelled_at"])
        if new:
            w.writeheader()
        w.writerows(rows)


def run(dry: bool, limit: int | None, timeout: float, mount_check: bool) -> int:
    configure_logging()
    base = os.environ.get("LLM_BASE_URL")
    if not base:
        print("LLM_BASE_URL is not set (it comes from .env).")
        return 1
    url = completion_url(base)
    if not dry and mount_check and not os.path.ismount(str(CSV_PATH.parent.parent)):
        print('REFUSED: the data folder is not mounted, the CSV would be lost with the container.\n'
              'Run with:  -v "<repo path with forward slashes>/data:/app/data"')
        return 1

    candidates = load_candidates(limit)
    print(f"{len(candidates)} unlabelled English postings to label ({'DRY RUN, nothing is saved' if dry else 'saving'})")
    if not candidates:
        return 0

    counts: Counter[str] = Counter()
    batch: list[dict] = []
    errors = 0
    t0 = time.monotonic()
    with httpx.Client(timeout=timeout) as client:
        for n, (pid, title, company, text) in enumerate(candidates, start=1):
            try:
                label, model = ask_llm(client, url, build_prompt(title, company, text))
            except (httpx.HTTPError, ValueError) as e:
                errors += 1
                print(f"  [{pid}] ERROR {type(e).__name__}: {str(e)[:200]}")
                if errors >= MAX_CONSECUTIVE_ERRORS:
                    print(f"STOPPED after {errors} errors in a row. Is the llama.cpp server up and listening on "
                          f"0.0.0.0? Tried: {url}")
                    break
                continue
            errors = 0
            counts[label] += 1
            print(f"  {n}/{len(candidates)} [{pid}] {title[:60]} -> {label}")
            if not dry:
                if save_label(pid, label):
                    batch.append({"id": pid, "llm_label": label, "model": model,
                                  "labelled_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
                if len(batch) >= 10:
                    append_csv(batch)
                    batch = []
    if batch:
        append_csv(batch)
    done = sum(counts.values())
    print("by class:", dict(counts))
    if done:
        print(f"{done} labelled, average {(time.monotonic() - t0) / done:.1f} s per posting")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="print predictions, save nothing")
    ap.add_argument("--limit", type=int, default=None, help="only the first N candidates")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--no-mount-check", action="store_true", help="tests only")
    a = ap.parse_args()
    raise SystemExit(run(a.dry, a.limit, a.timeout, not a.no_mount_check))
