"""
Long-running scheduler process: chains every pipeline stage in order and runs
the whole thing on an interval (from config/profile.yaml's
sources.scrape_interval_hours). This is what the `scheduler` compose service
runs (profile "scheduled" — see docker-compose.yml), replacing what would
otherwise be a Windows Task Scheduler entry or a cron job.

Each stage already wraps itself in run_stage() for observability (src/automation/
run_logger.py), and each stage already fails loudly-and-continues internally
(one bad posting doesn't kill a whole run) — so the scheduler's job is just
sequencing, not error recovery. If one stage fails outright (e.g. DB down), we
log it and skip straight to trying again next interval, rather than crashing
the daemon.

Run: python -m src.automation.scheduler
"""
from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler

from src.common.config import get_profile
from src.common.logging import configure_logging, get_logger
from src.llm_extraction.main import run as run_extraction
from src.ml.main import run as run_ml
from src.scoring.main import run as run_scoring
from src.scraper.main import run as run_scraper

logger = get_logger(__name__)

# Sheets writer needs credentials.json present — imported lazily inside the job
# so the scheduler can still start (and run everything else) without it.


def run_full_pipeline() -> None:
    stages = [
        ("scraper", run_scraper),
        ("llm_extraction", run_extraction),
        ("ml", run_ml),
        ("scoring", run_scoring),
    ]

    for name, fn in stages:
        try:
            logger.info("pipeline_stage_starting", stage=name)
            fn()
        except Exception as exc:
            logger.error("pipeline_stage_failed", stage=name, error=str(exc))
            # Continue to next stage rather than aborting — e.g. if scoring fails,
            # we still want the extraction/ml results persisted from this run.
            continue

    try:
        from src.automation.sheets_writer import run as run_sheets

        run_sheets()
    except FileNotFoundError:
        logger.warning(
            "sheets_writer_skipped",
            note="credentials.json not found — set up Google Sheets (docs/PHASE8.md) to enable reporting.",
        )
    except Exception as exc:
        logger.error("pipeline_stage_failed", stage="sheets_writer", error=str(exc))

    logger.info("pipeline_run_complete")


def main() -> None:
    configure_logging()
    profile = get_profile()
    interval_hours = profile.sources.scrape_interval_hours

    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_full_pipeline,
        "interval",
        hours=interval_hours,
        id="full_pipeline",
    )

    logger.info("scheduler_starting", interval_hours=interval_hours)

    # Run once immediately on startup, then let the interval take over — this is
    # the behavior you actually want for a long-running container: don't wait
    # a full interval before the first useful output.
    run_full_pipeline()

    scheduler.start()


if __name__ == "__main__":
    main()
