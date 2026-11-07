"""M2.6: how often does the LLM labeller disagree with MY hand labels? (no human work needed)

Runs the same prompt as scripts/llm_prelabel.py on the hand-labelled ('manual') postings and compares.
Nothing is saved to the database. The few hand-labelled postings whose titles are used as examples inside
the prompt are left out, because the model has seen their answers.

Run (llama.cpp server up; add --write and mount docs to keep the report):
    docker compose run --rm --no-deps -v "<repo>/docs:/app/docs" extractor python -m scripts.llm_vs_gold --write
"""
from __future__ import annotations

import argparse
import math
import os
from datetime import date
from pathlib import Path

import httpx
from sqlalchemy import select

from scripts.llm_prelabel import DEFINITIONS, ask_llm, build_prompt, completion_url
from src.common.db import session_scope
from src.common.logging import configure_logging
from src.common.models import Posting
from src.common.text_clean import clean_html_text

OUT_PATH = Path(__file__).resolve().parents[1] / "docs" / "LLM_LABEL_CHECK.md"


def example_titles() -> list[str]:
    block = DEFINITIONS.split("Examples (title -> category):")[1]
    return [ln.split(" -> ")[0].strip().lower() for ln in block.splitlines() if " -> " in ln]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% confidence interval for a proportion k/n."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    adj = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - adj) / denom, (centre + adj) / denom


def load_gold() -> list[dict]:
    with session_scope() as session:
        rows = session.execute(
            select(Posting.id, Posting.title, Posting.company, Posting.raw_text, Posting.category_label)
            .where(Posting.category_label_source == "manual").order_by(Posting.id)).all()
    return [{"id": r.id, "title": r.title or "", "company": r.company or "",
             "text": clean_html_text(r.raw_text), "hand": r.category_label} for r in rows]


def render(results: list[dict], skipped: list[dict], errors: int, today: str) -> str:
    n = len(results)
    k = sum(1 for r in results if r["hand"] == r["llm"])
    lo, hi = wilson(k, n)
    lines = [
        "# LLM label check", "",
        f"Generated {today} by `scripts/llm_vs_gold.py`.", "",
        "Question: how often does the local LLM labeller (Qwen3.5-9B, the one that labelled most postings) "
        "pick a different category than the hand label?", "",
        f"- Hand-labelled postings checked: **{n}**"
        + (f" ({len(skipped)} left out because their titles are examples inside the prompt"
           + (f", {errors} failed to get an answer" if errors else "") + ")." if skipped or errors else "."),
        f"- LLM agrees with the hand label on **{k} of {n}** = **{k / n:.0%}**" if n else "- No postings checked.",
    ]
    if n:
        lines.append(f"  (95% confidence interval {lo:.0%} to {hi:.0%}: with so few postings the real rate could be "
                     "anywhere in that range).")
    lines += ["", "## Disagreements", "", "| id | title | hand label | LLM label |", "|---|---|---|---|"]
    bad = [r for r in results if r["hand"] != r["llm"]]
    lines += [f"| {r['id']} | {r['title'][:60]} | {r['hand']} | {r['llm']} |" for r in bad] or ["| - | none | - | - |"]
    lines += ["", "## How to read this", "",
              "- A disagreement does not prove the LLM is wrong: the hand label is one person's opinion and several "
              "roles sit on the border between two categories.",
              "- These postings are the first ones in the database, not a random sample, and the hand labels contain "
              "mostly non-technical roles.",
              "- With this few postings the number is a rough guide only. Checking 40 more LLM-labelled postings by "
              "hand would narrow the interval a lot.", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write docs/LLM_LABEL_CHECK.md (docs must be mounted)")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--no-mount-check", action="store_true", help="tests only")
    a = ap.parse_args()
    configure_logging()
    base = os.environ.get("LLM_BASE_URL")
    if not base:
        print("LLM_BASE_URL is not set (it comes from .env).")
        return 1
    if a.write and not a.no_mount_check and not os.path.ismount(str(OUT_PATH.parent)):
        print('REFUSED: the docs folder is not mounted. Run with:  -v "<repo path with forward slashes>/docs:/app/docs"')
        return 1

    examples = example_titles()
    gold = load_gold()
    use = [g for g in gold if not any(g["title"].lower().startswith(e) for e in examples)]
    skipped = [g for g in gold if g not in use]
    print(f"{len(gold)} hand-labelled postings, {len(skipped)} left out (prompt examples), {len(use)} to check")

    results, errors = [], 0
    url = completion_url(base)
    with httpx.Client(timeout=a.timeout) as client:
        for g in use:
            try:
                llm, _ = ask_llm(client, url, build_prompt(g["title"], g["company"], g["text"]))
            except (httpx.HTTPError, ValueError) as e:
                errors += 1
                print(f"  [{g['id']}] ERROR {type(e).__name__}: {str(e)[:150]}")
                continue
            results.append({**g, "llm": llm})
            print(f"  [{g['id']}] {g['title'][:45]:45s} hand={g['hand']:24s} llm={llm:24s} {'ok' if llm == g['hand'] else 'DIFFERENT'}")
    md = render(results, skipped, errors, date.today().isoformat())
    print("\n" + md)
    if a.write and results:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(md, encoding="utf-8")
        print(f"written: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
