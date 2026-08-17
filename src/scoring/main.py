"""
Scores every in-scope posting using a three-tier fallback, checked in this
order per posting:

  1. llm  — fit_score judged directly by the extraction-stage LLM against the
     candidate's skills (see src/llm_extraction/extractor.py). Preferred when
     present: it judges by domain/semantic relevance, not exact string
     matching, so it correctly treats e.g. "LLMs, NLP, embeddings" as a match
     for a candidate skill of "AI/ML".
  2. v2 learned model — trained on your own past ratings, once you've rated
     enough postings AND that model beats the "guess the average" baseline
     (see src/scoring/learned_scorer.py's CV quality gate).
  3. v1 formula — always available, deterministic, and the original audit
     trail (see src/scoring/formula_scorer.py). Used only when a posting has
     neither an LLM score (extraction failed, or the model didn't return one)
     nor a learned model available.

Run: python -m src.scoring.main
"""
from __future__ import annotations

from sqlalchemy import select, update

from src.automation.run_logger import run_stage
from src.common.config import get_profile
from src.common.db import session_scope
from src.common.logging import configure_logging, get_logger
from src.common.models import Posting
from src.scoring.formula_scorer import compute_v1_score
from src.scoring.learned_scorer import load_learned_scorer, predict_learned_score

logger = get_logger(__name__)


def run() -> None:
    configure_logging()
    with run_stage("scoring") as run_ctx:
        profile = get_profile()
        learned_model = load_learned_scorer()

        with session_scope() as session:
            all_postings = session.scalars(select(Posting).order_by(Posting.id)).all()
            postings = [p for p in all_postings if p.cluster_id is not None]
            out_of_scope_ids = [p.id for p in all_postings if p.cluster_id is None]

            # Self-heal stale fit_score values (2026-08-16) — same bug class as
            # the cluster_id staleness fixed in src/ml/main.py: this query only
            # ever WRITES fit_score for the current in-scope set, but never
            # CLEARED it for postings that fell out of scope. Non-English
            # postings (Suporte N1 REMOTO, ADVPL Júnior, dozens of German
            # MY Humancapital GmbH listings) still carried fit_score values
            # from before the cluster_id filter existed here, and
            # sheets_writer.py's WHERE fit_score IS NOT NULL had no way to
            # tell a stale score from a real one — it wrote all 200 rows to
            # the sheet instead of the intended 96.
            if out_of_scope_ids:
                session.execute(
                    update(Posting).where(Posting.id.in_(out_of_scope_ids)).values(fit_score=None)
                )
                logger.info("stale_fit_score_cleared", n=len(out_of_scope_ids))

            n_out_of_scope = len(out_of_scope_ids)
            if n_out_of_scope:
                logger.info(
                    "scoring_scope_filtered",
                    scored=len(postings),
                    excluded_non_english_or_unprocessed=n_out_of_scope,
                )

            llm_count, v1_count, v2_count = 0, 0, 0
            for posting in postings:
                v1_score = compute_v1_score(posting, profile)

                if posting.llm_fit_score is not None:
                    # Take the max, not a blind override (2026-08-16) — a
                    # literal skill match (e.g. "Docker" appearing in both
                    # required_skills and candidate.skills) should never
                    # score below what plain substring matching would give
                    # it, even if the LLM's judgment call landed low that
                    # pass. A 9B local model doing continuous 0.0-1.0
                    # calibration has real variance near the low-relevance
                    # boundary — we saw this directly: "Docker, Kubernetes,
                    # CI/CD" and "Python, Databricks, DBT, Airflow" postings,
                    # both with an exact candidate-skill match, scored 0.0
                    # from the LLM alone. v1's skill_match_score() acts as a
                    # floor here — it can only pull the combined score UP
                    # toward what a literal match deserves, never down. The
                    # LLM still gets full credit for the matches ONLY it can
                    # catch (e.g. "NLP"/"LLMs" -> "AI/ML" semantic overlap
                    # that no substring match would find), since v1 would
                    # score those near-zero and max() keeps the LLM's higher
                    # number in that case.
                    posting.fit_score = max(posting.llm_fit_score, v1_score)
                    llm_count += 1
                elif learned_model is not None:
                    posting.fit_score = predict_learned_score(posting, profile, learned_model)
                    v2_count += 1
                else:
                    posting.fit_score = v1_score
                    v1_count += 1

            run_ctx.rows_processed = len(postings)

        logger.info(
            "scoring_complete",
            total=len(postings),
            scored_with_llm=llm_count,
            scored_with_v1=v1_count,
            scored_with_v2=v2_count,
        )


if __name__ == "__main__":
    run()