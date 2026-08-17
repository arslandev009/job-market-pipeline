"""
Generic Playwright-based adapter for sources that don't offer an API.

This is deliberately a *template*, not tied to one specific job board — job board
HTML changes constantly and hardcoding one site's selectors here would make this
file stale the moment that site redesigns. Instead: point it at a list of posting
URLs (`config/scrape_targets.yaml`) and a CSS-selector map, and it scrapes any
site that follows a "posting page has title/company/body" shape.

This is where the async/concurrency requirement actually lives: a bounded
Semaphore caps how many browser pages run at once, so we scrape several postings
in parallel without hammering the target site or exhausting local RAM.

Before pointing this at a real site: check that site's /robots.txt and terms of
service. Prefer an API if one exists (see remoteok.py / arbeitnow.py for why).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import yaml
from playwright.async_api import Page, async_playwright

from src.common.config import get_settings
from src.common.logging import get_logger
from src.scraper.sources.base import RawPosting

logger = get_logger(__name__)

TARGETS_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "scrape_targets.yaml"


class GenericPlaywrightSource:
    """
    Config-driven scraper. `config/scrape_targets.yaml` defines:

        source_name: "example_board"
        base_delay_seconds: 1.5
        urls:
          - "https://example.com/jobs/123"
        selectors:
          title: "h1.job-title"
          company: ".company-name"
          body: ".job-description"
    """

    def __init__(self, config_path: Path = TARGETS_CONFIG_PATH):
        self.config_path = config_path

    def _load_config(self) -> dict[str, Any] | None:
        if not self.config_path.exists():
            logger.info(
                "generic_playwright_no_config",
                msg=f"No {self.config_path.name} found — skipping scraped source. "
                "Copy scrape_targets.example.yaml to enable it.",
            )
            return None
        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    async def fetch(self) -> list[RawPosting]:
        config = self._load_config()
        if not config:
            return []

        self.name = config.get("source_name", "generic_scraped")
        urls: list[str] = config.get("urls", [])
        selectors: dict[str, str] = config.get("selectors", {})
        settings = get_settings()

        semaphore = asyncio.Semaphore(settings.scraper_max_concurrency)
        postings: list[RawPosting] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                tasks = [
                    self._scrape_one(browser, url, selectors, semaphore, settings)
                    for url in urls
                ]
                results = await asyncio.gather(*tasks)
                postings = [r for r in results if r is not None]
            finally:
                await browser.close()

        logger.info("generic_playwright_fetch_complete", count=len(postings), source=self.name)
        return postings

    async def _scrape_one(
        self,
        browser,
        url: str,
        selectors: dict[str, str],
        semaphore: asyncio.Semaphore,
        settings,
    ) -> RawPosting | None:
        async with semaphore:
            page: Page | None = None
            try:
                page = await browser.new_page()
                await page.goto(url, timeout=settings.scraper_timeout_ms)

                title = await self._text_or_none(page, selectors.get("title"))
                company = await self._text_or_none(page, selectors.get("company"))
                body = await self._text_or_none(page, selectors.get("body"))

                # Standard scraping etiquette: don't hammer the target server,
                # even though the semaphore already caps concurrency.
                await asyncio.sleep(settings.scraper_request_delay_seconds)

                return RawPosting(
                    source=self.name,
                    url=url,
                    title=title,
                    company=company,
                    raw_text=" ".join(p for p in [title, company, body] if p),
                    raw_payload={"scraped_selectors": selectors},
                )
            except Exception as exc:
                # Fail loudly-and-skip, never crash the whole run over one bad page —
                # real sites 404, redirect, or change layout constantly.
                logger.warning("generic_playwright_page_failed", url=url, error=str(exc))
                return None
            finally:
                if page is not None:
                    await page.close()

    @staticmethod
    async def _text_or_none(page: Page, selector: str | None) -> str | None:
        if not selector:
            return None
        try:
            el = await page.query_selector(selector)
            if not el:
                return None
            text = await el.inner_text()
            return text.strip() or None
        except Exception:
            return None
