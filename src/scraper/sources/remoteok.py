"""
RemoteOK exposes a public, no-auth-required JSON API — no scraping needed, no ToS
gray area. This is our "reliable baseline" source: fast, structured, never breaks
on a CSS selector change. Real pipelines always prefer an API over scraping when
one exists (see docs/PHASE3.md).
"""
from __future__ import annotations

import httpx

from src.common.logging import get_logger
from src.scraper.sources.base import RawPosting

logger = get_logger(__name__)

API_URL = "https://remoteok.com/api"


class RemoteOKSource:
    name = "remoteok"

    async def fetch(self) -> list[RawPosting]:
        postings: list[RawPosting] = []
        headers = {"User-Agent": "job-market-pipeline/1.0 (personal project)"}

        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            try:
                resp = await client.get(API_URL)
                resp.raise_for_status()
                items = resp.json()
            except Exception as exc:
                logger.error("remoteok_fetch_failed", error=str(exc))
                return postings

        # First element is a metadata/legal block, not a posting — skip it.
        for item in items[1:] if items else []:
            try:
                if not item.get("url") or not item.get("id"):
                    continue
                text_parts = [
                    item.get("position", ""),
                    item.get("company", ""),
                    item.get("description", ""),
                    " ".join(item.get("tags", []) or []),
                ]
                postings.append(
                    RawPosting(
                        source=self.name,
                        url=item["url"],
                        title=item.get("position"),
                        company=item.get("company"),
                        raw_text=" ".join(p for p in text_parts if p),
                        raw_payload=item,
                    )
                )
            except Exception as exc:
                logger.warning("remoteok_item_skipped", error=str(exc), item_id=item.get("id"))
                continue

        logger.info("remoteok_fetch_complete", count=len(postings))
        return postings
