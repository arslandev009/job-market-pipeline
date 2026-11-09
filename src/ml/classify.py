"""
Category classifier: a logistic regression over TF-IDF features, trained on
whatever postings you've hand-labeled (via scripts/label_batch.py) and applied
to everything else.

This intentionally starts small — you need only ~30-50 labeled examples across
2-4 categories (e.g. "frontend", "backend", "fullstack", "data/ml") for this to
produce a usable classifier. It's a real example of the classic bootstrap
problem in applied ML: no labels yet → label a small seed set by hand → train →
use the model's own high-confidence predictions to help you label faster next
round (semi-supervised expansion — noted in docs/PHASE6.md, not automated here
on purpose, since blindly trusting your own model's labels back into training
without a human check is how label noise compounds).
"""
from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression

from src.common.logging import get_logger
from src.ml.features import build_vectorizer

logger = get_logger(__name__)

MODEL_DIR = Path(__file__).resolve().parents[2] / "data" / "models"
CLASSIFIER_PATH = MODEL_DIR / "category_classifier.joblib"
VECTORIZER_PATH = MODEL_DIR / "category_vectorizer.joblib"

MIN_LABELED_EXAMPLES = 20


def train_classifier(labeled_df: pd.DataFrame) -> tuple[LogisticRegression, object] | None:
    """labeled_df must have columns: raw_text, category_label."""
    if len(labeled_df) < MIN_LABELED_EXAMPLES:
        logger.warning(
            "classifier_training_skipped",
            n_labeled=len(labeled_df),
            required=MIN_LABELED_EXAMPLES,
            note="Label more postings with scripts/label_batch.py before training.",
        )
        return None

    vectorizer = build_vectorizer()
    X = vectorizer.fit_transform(labeled_df["raw_text"].fillna(""))
    y = labeled_df["category_label"]

    clf = LogisticRegression(C=3.0, max_iter=2000, class_weight="balanced")

    # The accuracy estimate lives in scripts/evaluate_classifier.py: there the vectorizer is fitted inside
    # every fold. A cross_val_score on an already-vectorized matrix lets the vocabulary leak into the folds.

    clf.fit(X, y)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, CLASSIFIER_PATH)
    joblib.dump(vectorizer, VECTORIZER_PATH)
    logger.info("classifier_trained", n_examples=len(labeled_df), classes=sorted(y.unique()))

    return clf, vectorizer


def load_classifier() -> tuple[LogisticRegression, object] | None:
    if not CLASSIFIER_PATH.exists() or not VECTORIZER_PATH.exists():
        return None
    return joblib.load(CLASSIFIER_PATH), joblib.load(VECTORIZER_PATH)


def predict_categories(df: pd.DataFrame, clf: LogisticRegression, vectorizer) -> pd.Series:
    X = vectorizer.transform(df["raw_text"].fillna(""))
    return pd.Series(clf.predict(X), index=df.index)
