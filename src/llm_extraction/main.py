"""
Batch-runs LLM extraction over every posting that hasn't been extracted yet.

Run: python -m src.llm_extraction.main

CHANGE 2026-08-16: now passes profile.candidate.skills into extract_fields()
so the model can judge candidate fit directly against the same posting text
it's already reading for structured-field extraction, and writes the model's
llm_fit_score / llm_fit_reasoning back onto the posting alongside the other
extracted fields. See src/llm_extraction/extractor.py's module docstring and
src/scoring/main.py's three-tier fallback for the full reasoning.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from src.automation.run_logger import run_stage
from src.common.config import get_profile
from src.common.db import session_scope
from src.common.logging import configure_logging, get_logger
from src.common.models import Posting
from src.llm_extraction.extractor import extract_fields

logger = get_logger(__name__)


def run() -> None:
    configure_logging()
    with run_stage("llm_extraction") as run_ctx:
        profile = get_profile()

        with session_scope() as session:
            pending = session.scalars(
                select(Posting).where(Posting.extracted_at.is_(None))
            ).all()

            logger.info("extraction_starting", pending_count=len(pending))

            processed = 0
            for posting in pending:
                result = extract_fields(posting.raw_text or "", profile.candidate.skills)
                if result is None:
                    logger.warning("extraction_skipped", posting_id=posting.id)
                    continue

                posting.seniority = result.seniority
                posting.remote_or_onsite = result.remote_or_onsite
                posting.salary_min = result.salary_min
                posting.salary_max = result.salary_max
                posting.location = result.location
                posting.required_skills = result.required_skills
                posting.llm_fit_score = result.fit_score
                posting.llm_fit_reasoning = result.fit_reasoning
                posting.extracted_at = dt.datetime.now(dt.timezone.utc)
                processed += 1

                if processed % 10 == 0:
                    logger.info("extraction_progress", processed=processed, total=len(pending))

            run_ctx.rows_processed = processed
            logger.info("extraction_complete", processed=processed, total=len(pending))


if __name__ == "__main__":
    run()