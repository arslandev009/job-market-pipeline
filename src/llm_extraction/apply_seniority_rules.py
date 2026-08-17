"""
Fast pass: fills seniority for postings the LLM left as "unknown", using
title keyword rules. Never touches postings with a non-"unknown" seniority.

Run: python -m src.llm_extraction.apply_seniority_rules
"""
from __future__ import annotations

from sqlalchemy import select

from src.common.db import session_scope
from src.common.logging import configure_logging, get_logger
from src.common.models import Posting
from src.llm_extraction.seniority_rules import infer_seniority_from_title

logger = get_logger(__name__)


def run() -> None:
    configure_logging()
    with session_scope() as session:
        postings = session.scalars(
            select(Posting).where(Posting.seniority == "unknown")
        ).all()

        updated = 0
        for posting in postings:
            inferred = infer_seniority_from_title(posting.title)
            if inferred:
                posting.seniority = inferred
                posting.seniority_source = "title_rule"
                updated += 1

        logger.info("seniority_rules_applied", checked=len(postings), updated=updated)
        print(f"Checked {len(postings)} 'unknown' postings, updated {updated} via title rules.")


if __name__ == "__main__":
    run()