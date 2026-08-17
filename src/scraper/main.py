"""
Orchestrates every enabled source concurrently, dedupes by URL, and upserts into
Postgres. This is the entrypoint the `scraper` container runs.

Run: python -m src.scraper.main
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os

from sqlalchemy.dialects.postgresql import insert

from src.automation.run_logger import run_stage
from src.common.config import get_profile
from src.common.db import session_scope
from src.common.logging import configure_logging, get_logger
from src.common.models import Posting
from src.scraper.registry import build_sources
from src.scraper.sources.base import RawPosting

logger = get_logger(__name__)


async def gather_all_postings() -> list[RawPosting]:
    profile = get_profile()
    sources = build_sources(profile.sources.enabled)

    # SCRAPER_MAX_PER_SOURCE controls how many postings each source keeps.
    # Unset or 0 = unlimited (original behavior). Set e.g. to 25 for a fast
    # end-to-end smoke test instead of a full multi-hour run.
    max_per_source = int(os.environ.get("SCRAPER_MAX_PER_SOURCE", "0") or "0")

    logger.info(
        "scrape_starting",
        sources=[s.name for s in sources],
        max_per_source=max_per_source or "unlimited",
    )
    results = await asyncio.gather(
        *(s.fetch() for s in sources), return_exceptions=True
    )

    all_postings: list[RawPosting] = []
    for source, result in zip(sources, results):
        if isinstance(result, Exception):
            # One source failing should never take down the whole scrape run.
            logger.error("source_failed_entirely", source=source.name, error=str(result))
            continue
        if max_per_source:
            result = result[:max_per_source]
        all_postings.extend(result)

    return all_postings


def dedupe_by_url(postings: list[RawPosting]) -> list[RawPosting]:
    seen: dict[str, RawPosting] = {}
    for p in postings:
        seen[p.url] = p  # last one wins; fine since sources rarely overlap URLs
    return list(seen.values())


def upsert_postings(postings: list[RawPosting]) -> int:
    """Insert new postings, ignore ones we've already scraped (by URL)."""
    if not postings:
        return 0

    with session_scope() as session:
        rows = [
            {
                "source": p.source,
                "url": p.url,
                "title": p.title,
                "company": p.company,
                "raw_text": p.raw_text,
                "raw_payload": p.raw_payload,
                "scraped_at": dt.datetime.now(dt.timezone.utc),
            }
            for p in postings
        ]
        stmt = insert(Posting).values(rows)
        stmt = stmt.on_conflict_do_nothing(constraint="uq_postings_url").returning(Posting.id)
        result = session.execute(stmt)
        return len(result.fetchall())


def run() -> None:
    configure_logging()
    with run_stage("scraper") as run_ctx:
        postings = asyncio.run(gather_all_postings())
        deduped = dedupe_by_url(postings)
        inserted = upsert_postings(deduped)
        run_ctx.rows_processed = inserted
        logger.info(
            "scrape_complete",
            fetched=len(postings),
            deduped=len(deduped),
            newly_inserted=inserted,
        )


if __name__ == "__main__":
    run()