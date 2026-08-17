"""
Minimal pipeline observability: every stage wraps its work in `run_stage(name)`,
which writes a row to the `runs` table on start, and updates it with
status/rows_processed/error on finish. This is Phase 9's "basic observability"
requirement — not a full metrics stack, just enough that `SELECT * FROM runs
ORDER BY started_at DESC` tells you exactly what ran, when, and whether it worked.
"""
from __future__ import annotations

import datetime as dt
from contextlib import contextmanager
from dataclasses import dataclass

from src.common.db import session_scope
from src.common.logging import get_logger
from src.common.models import PipelineRun

logger = get_logger(__name__)


@dataclass
class RunContext:
    rows_processed: int = 0


@contextmanager
def run_stage(stage_name: str):
    started_at = dt.datetime.now(dt.timezone.utc)
    ctx = RunContext()

    with session_scope() as session:
        run_row = PipelineRun(stage=stage_name, started_at=started_at, status="running")
        session.add(run_row)
        session.flush()
        run_id = run_row.id

    try:
        yield ctx
        with session_scope() as session:
            row = session.get(PipelineRun, run_id)
            row.status = "success"
            row.finished_at = dt.datetime.now(dt.timezone.utc)
            row.rows_processed = ctx.rows_processed
    except Exception as exc:
        with session_scope() as session:
            row = session.get(PipelineRun, run_id)
            row.status = "failed"
            row.finished_at = dt.datetime.now(dt.timezone.utc)
            row.rows_processed = ctx.rows_processed
            row.error_message = str(exc)[:2000]
        logger.error("stage_failed", stage=stage_name, error=str(exc))
        raise
