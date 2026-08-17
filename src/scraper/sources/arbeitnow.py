"""
Arbeitnow's public job board API — our second API source. Having two API sources
before we add a scraped one matters for Phase 4's EDA: it lets us check source
imbalance and writing-style variance with data that's already reliable, so we
know any weirdness later is coming from the scraped source, not from these.
"""
from __future__ import annotations

import httpx

from src.common.logging import get_logger
from src.scraper.sources.base import RawPosting

logger = get_logger(__name__)

API_URL = "https://www.arbeitnow.com/api/job-board-api"


class ArbeitnowSource:
    name = "arbeitnow"

    async def fetch(self) -> list[RawPosting]:
        postings: list[RawPosting] = []
        headers = {"User-Agent": "job-market-pipeline/1.0 (personal project)"}

        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            try:
                resp = await client.get(API_URL)
                resp.raise_for_status()
                payload = resp.json()
                items = payload.get("data", [])
            except Exception as exc:
                logger.error("arbeitnow_fetch_failed", error=str(exc))
                return postings

        for item in items:
            try:
                url = item.get("url")
                if not url:
                    continue
                text_parts = [
                    item.get("title", ""),
                    item.get("company_name", ""),
                    item.get("description", ""),
                    " ".join(item.get("tags", []) or []),
                ]
                postings.append(
                    RawPosting(
                        source=self.name,
                        url=url,
                        title=item.get("title"),
                        company=item.get("company_name"),
                        raw_text=" ".join(p for p in text_parts if p),
                        raw_payload=item,
                    )
                )
            except Exception as exc:
                logger.warning("arbeitnow_item_skipped", error=str(exc))
                continue

        logger.info("arbeitnow_fetch_complete", count=len(postings))
        return postings
