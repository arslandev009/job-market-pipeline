"""
v2 scorer: replaces the v1 formula's *guessed* weights with weights learned from
your own hand-ratings (the manual_rating field, filled in via
scripts/label_batch.py). This is a small, deliberately simple model — Ridge
regression over the same three sub-scores v1 uses, plus salary/skill-count as
raw numeric features. The point isn't model sophistication, it's demonstrating
the heuristic → learned progression a real internal tool goes through (see
docs/ARCHITECTURE.md §7).

Needs at least ~15 manually-rated postings before it's worth training — fewer
than that and Ridge will just overfit noise. Falls back to v1 automatically
until then (see src/scoring/main.py).

CHANGE 2026-08-14: added a cross-validated R^2 quality gate. A 28-example
training run scored R^2 = -2.358 (worse than just guessing the average rating
every time), and the old code saved that model anyway — the only existing
guard was on example COUNT, not quality. Without this gate, main.py would
have silently switched every posting from the working v1 formula to a
demonstrably worse model, with nothing but a log line to notice it by.
"""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import cross_val_score

from src.common.config import Profile
from src.common.logging import get_logger
from src.common.models import Posting
from src.scoring.formula_scorer import (
    location_fit_score,
    salary_fit_score,
    skill_match_score,
)

logger = get_logger(__name__)

MODEL_DIR = Path(__file__).resolve().parents[2] / "data" / "models"
MODEL_PATH = MODEL_DIR / "learned_scorer.joblib"
MIN_RATED_EXAMPLES = 15


def _build_features(posting: Posting, profile: Profile) -> list[float]:
    return [
        skill_match_score(posting, profile.candidate.skills),
        salary_fit_score(posting, profile.candidate.preferred_salary_min),
        location_fit_score(posting, profile.candidate.preferred_location),
        len(posting.required_skills or []),
    ]


def train_learned_scorer(rated_postings: list[Posting], profile: Profile) -> Ridge | None:
    if len(rated_postings) < MIN_RATED_EXAMPLES:
        logger.warning(
            "learned_scorer_training_skipped",
            n_rated=len(rated_postings),
            required=MIN_RATED_EXAMPLES,
            note="Rate more postings with scripts/label_batch.py before training v2.",
        )
        return None

    X = np.array([_build_features(p, profile) for p in rated_postings])
    y = np.array([p.manual_rating for p in rated_postings])

    model = Ridge(alpha=1.0)
    cv_folds = min(5, len(rated_postings))
    if cv_folds >= 3:
        scores = cross_val_score(model, X, y, cv=cv_folds)
        mean_r2 = scores.mean()
        logger.info("learned_scorer_cv_r2", mean=round(mean_r2, 3), folds=cv_folds)

        # R^2 <= 0 means this model predicts fit WORSE than just guessing the
        # average rating every time. Refuse to save it - see module docstring.
        if mean_r2 <= 0:
            logger.warning(
                "learned_scorer_training_rejected",
                mean_r2=round(mean_r2, 3),
                note="Cross-validated R^2 is at or below 0 - refusing to save "
                "this model so main.py keeps falling back to v1. Rate more "
                "postings (aim for 40+) and retrain, or check whether "
                "ratings are noisy/inconsistent.",
            )
            return None

    model.fit(X, y)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    logger.info("learned_scorer_trained", n_examples=len(rated_postings))
    return model


def load_learned_scorer() -> Ridge | None:
    if not MODEL_PATH.exists():
        return None
    return joblib.load(MODEL_PATH)


def predict_learned_score(posting: Posting, profile: Profile, model: Ridge) -> float:
    features = np.array([_build_features(posting, profile)])
    raw = model.predict(features)[0]
    # Ridge regresses toward the 1-5 rating scale; normalize to 0-1 to match v1's range.
    normalized = (raw - 1) / 4
    return float(np.clip(normalized, 0.0, 1.0))