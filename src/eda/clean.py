"""
Step 3 of the EDA workflow: clean raw_text into clean_text. Every transformation
here exists because diagnose.py found a specific, named problem — this file
should never grow a "just in case" cleaning step that isn't traceable back to
a diagnosis. raw_text itself is never touched (see docs/ARCHITECTURE.md §2):
clean_text is a separate, derived column, so re-running this later with better
logic never requires re-scraping anything.

Run: python -m src.eda.clean
"""
from __future__ import annotations

import datetime as dt
import re

import ftfy
from bs4 import BeautifulSoup
from sqlalchemy import select

from src.common.db import session_scope
from src.common.logging import configure_logging, get_logger
from src.common.models import Posting

logger = get_logger(__name__)

WHITESPACE_COLLAPSE_PATTERN = re.compile(r"[ \t]{2,}")
BLANK_LINE_COLLAPSE_PATTERN = re.compile(r"\n{2,}")

# From diagnose.py's text_length_outliers check — a posting shorter than this
# has essentially no content for the LLM extractor to work with; one longer
# than this is treated as suspicious rather than automatically truncated,
# since a long posting might be entirely legitimate (see docs/PHASE4.md).
MIN_USEFUL_LENGTH = 40
MAX_EXPECTED_LENGTH = 6000


def fix_encoding(text: str) -> str:
    """Fix for: encoding corruption (mojibake) found by diagnose.py's
    check_encoding_corruption — text like 'weâ\\x80\\x99ve' that should read
    'we've'. Uses ftfy (the standard tool for this, not a hand-rolled fix)
    because correctly reversing a UTF-8-decoded-as-Latin-1 mistake requires
    real heuristics about which byte sequences are "clearly" broken UTF-8 —
    getting it wrong risks corrupting text that was already fine."""
    if not text:
        return text
    return ftfy.fix_text(text)


def strip_html(text: str) -> str:
    """Fix for: HTML contamination (RemoteOK's own docs confirm description
    fields contain raw HTML). BeautifulSoup over regex because regex-based tag
    stripping breaks on malformed/nested HTML in ways that silently corrupt
    text; BeautifulSoup's parser handles that correctly."""
    if not text:
        return text
    return BeautifulSoup(text, "html.parser").get_text(separator=" ")


def normalize_whitespace(text: str) -> str:
    """Fix for: whitespace irregularities found by diagnose.py — multiple
    spaces/tabs and repeated blank lines, largely a side effect of stripping
    HTML block elements (each closed tag can leave a run of whitespace behind)."""
    if not text:
        return text
    text = WHITESPACE_COLLAPSE_PATTERN.sub(" ", text)
    text = BLANK_LINE_COLLAPSE_PATTERN.sub("\n", text)
    return text.strip()


def classify_length(clean_text: str) -> str:
    """Fix for: text length outliers found by diagnose.py. Flags rather than
    deletes — Phase 5's extractor and Phase 6's classifier can both choose to
    skip flagged rows, but nothing here destroys data a later phase might still
    find useful."""
    length = len(clean_text)
    if length < MIN_USEFUL_LENGTH:
        return "too_short"
    if length > MAX_EXPECTED_LENGTH:
        return "too_long"
    return "ok"


def mark_near_duplicates(postings: list[Posting]) -> set[int]:
    """Fix for: near-duplicate postings found by diagnose.py (same title+company
    cross-posted under two sources). Flags the *second* occurrence only — keeps
    exactly one canonical copy live for downstream phases, without deleting the
    other (deleting scraped data is treated as a one-way door we avoid; flagging
    is reversible)."""
    seen: dict[str, int] = {}
    duplicate_ids: set[int] = set()

    for posting in sorted(postings, key=lambda p: p.scraped_at):
        key = f"{(posting.title or '').strip().lower()}||{(posting.company or '').strip().lower()}"
        if key == "||":
            continue
        if key in seen:
            duplicate_ids.add(posting.id)
        else:
            seen[key] = posting.id

    return duplicate_ids


def clean_one(raw_text: str) -> str:
    # Order matters: fix encoding first, since garbled bytes can otherwise
    # interfere with HTML tag detection; then strip HTML; then normalize
    # whatever whitespace either step left behind.
    text = fix_encoding(raw_text or "")
    text = strip_html(text)
    return normalize_whitespace(text)


def run() -> None:
    configure_logging()
    with session_scope() as session:
        postings = session.scalars(select(Posting)).all()

        if not postings:
            logger.warning("clean_no_data", note="Run the scraper first.")
            return

        duplicate_ids = mark_near_duplicates(postings)
        now = dt.datetime.now(dt.timezone.utc)

        stats = {"ok": 0, "too_short": 0, "too_long": 0, "near_duplicate": 0}

        for posting in postings:
            cleaned = clean_one(posting.raw_text)
            posting.clean_text = cleaned
            posting.text_quality_flag = classify_length(cleaned)
            posting.is_near_duplicate = posting.id in duplicate_ids
            posting.cleaned_at = now

            stats[posting.text_quality_flag] += 1
            if posting.is_near_duplicate:
                stats["near_duplicate"] += 1

        logger.info("clean_complete", total=len(postings), **stats)
        print("\n=== CLEANING SUMMARY ===")
        print(f"Total postings cleaned: {len(postings)}")
        print(f"  quality=ok:        {stats['ok']}")
        print(f"  quality=too_short: {stats['too_short']}")
        print(f"  quality=too_long:  {stats['too_long']}")
        print(f"  near duplicates flagged: {stats['near_duplicate']}")


if __name__ == "__main__":
    run()