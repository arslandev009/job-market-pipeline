"""
Pulls every posting you've manually rated (the fit-rating prompt in
scripts/label_batch.py) and trains the v2 learned scorer on it.

Deliberately a separate, manually-triggered script rather than something
src/scoring/main.py runs automatically — same reasoning as
scripts/train_classifier.py: training should happen once you've built a real
rated batch, not silently re-trigger and retrain on every scoring run.

Run: docker compose run --rm scorer python -m scripts.train_scorer
"""
from __future__ import annotations

from sqlalchemy import select

from src.common.config import get_profile
from src.common.db import session_scope
from src.common.logging import configure_logging, get_logger
from src.common.models import Posting
from src.scoring.learned_scorer import train_learned_scorer

logger = get_logger(__name__)


def run() -> None:
    configure_logging()
    profile = get_profile()

    with session_scope() as session:
        # order_by(Posting.id) for the same reason src/ml/main.py needed it —
        # an unordered SELECT can return rows in a different sequence between
        # runs, and Ridge's cross_val_score folds (like KMeans' centroid init
        # in Phase 6) are order-sensitive, so this keeps CV results
        # reproducible run to run.
        rated = session.scalars(
            select(Posting).where(Posting.manual_rating.is_not(None)).order_by(Posting.id)
        ).all()

        if not rated:
            logger.warning(
                "train_scorer_no_data",
                note="No rated postings found. Rate some first: "
                "docker compose run --rm ml python -m scripts.label_batch --n 30",
            )
            return

        model = train_learned_scorer(rated, profile)

    if model is None:
        return  # train_learned_scorer already logged why (not enough examples yet)

    logger.info("train_scorer_complete", n_rated=len(rated))


if __name__ == "__main__":
    run()