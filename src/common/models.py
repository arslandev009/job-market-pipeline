"""
ORM models. These mirror the Alembic migrations exactly — migrations are the
source of truth for the actual DB schema, this file is the Python-side mapping
used by the rest of the app to read/write without hand-written SQL everywhere.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    ARRAY,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Posting(Base):
    __tablename__ = "postings"
    __table_args__ = (UniqueConstraint("url", name="uq_postings_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    company: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    scraped_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="now()", index=True
    )

    # Phase 4 — cleaning (see src/eda/clean.py). raw_text above is NEVER modified;
    # these are the derived, replayable outputs of the cleaning step.
    clean_text: Mapped[str | None] = mapped_column(Text)
    is_near_duplicate: Mapped[bool | None] = mapped_column(default=False)
    text_quality_flag: Mapped[str | None] = mapped_column(String)  # 'ok' | 'too_short' | 'too_long'
    cleaned_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    # Phase 5 — LLM extraction
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    seniority: Mapped[str | None] = mapped_column(String)
    seniority_source: Mapped[str | None] = mapped_column(String)  # 'llm' | 'title_rule'
    remote_or_onsite: Mapped[str | None] = mapped_column(String)
    required_skills: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    location: Mapped[str | None] = mapped_column(Text)
    extracted_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    # Phase 5b — LLM-judged candidate fit, added 2026-08-16. Computed in the
    # same extraction call as everything else above (see
    # src/llm_extraction/extractor.py) rather than a separate scoring-stage
    # LLM call, so it costs zero extra round-trips. Nullable: falls back to
    # the v1 formula (src/scoring/formula_scorer.py) via src/scoring/main.py's
    # three-tier fallback when extraction fails or the model doesn't return a
    # score for a given posting.
    llm_fit_score: Mapped[float | None] = mapped_column(Float)
    llm_fit_reasoning: Mapped[str | None] = mapped_column(Text)

    # Phase 6 — classical ML
    category_label: Mapped[str | None] = mapped_column(String)
    category_label_source: Mapped[str | None] = mapped_column(String)  # 'manual' | 'llm' | 'model'
    cluster_id: Mapped[int | None] = mapped_column(Integer)

    # Phase 7 — scoring
    fit_score: Mapped[float | None] = mapped_column(Float)
    manual_rating: Mapped[int | None] = mapped_column(Integer)  # 1-5, for v2 training

    # Phase 8 — reporting
    reported_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class PipelineRun(Base):
    """Basic observability: one row per pipeline stage execution (Phase 9)."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stage: Mapped[str] = mapped_column(String, nullable=False, index=True)
    started_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True))
    finished_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    status: Mapped[str] = mapped_column(String, default="running")  # running|success|failed
    rows_processed: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)