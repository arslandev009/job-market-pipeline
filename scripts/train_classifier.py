"""
Pulls every hand- or LLM-labeled posting (--manual-only for hand labels only) out of Postgres, cleans the text the same
way every other stage does (HTML/boilerplate stripped, English-only filtered),
and trains the category classifier on it via src.ml.classify.train_classifier.

This is deliberately a separate, manually-triggered script rather than
something ml/main.py runs automatically — training should happen once you've
hand-labeled a real batch (see scripts/label_batch.py), not silently
re-trigger on every pipeline run and retrain on a shifting label set.

Run: docker compose run --rm ml python -m scripts.train_classifier
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import select

from src.common.db import get_engine
from src.common.language import is_english
from src.common.logging import configure_logging, get_logger
from src.common.models import Posting
from src.common.text_clean import clean_html_text
from src.ml.classify import train_classifier

logger = get_logger(__name__)


def run(manual_only: bool = False) -> None:
    configure_logging()
    sources = ["manual"] if manual_only else ["manual", "llm"]
    engine = get_engine()
    df = pd.read_sql(
        select(Posting).where(Posting.category_label_source.in_(sources)).order_by(Posting.id),
        engine,
        index_col="id",
    )

    if df.empty:
        logger.warning(
            "train_classifier_no_data",
            note="No manually-labeled postings found. Label some first: "
            "docker compose run --rm ml python -m scripts.label_batch --n 30",
        )
        return

    # Same cleaning pipeline as clustering/elbow-curve (src/ml/main.py,
    # scripts/elbow_curve.py) — the classifier needs to train on the exact
    # kind of text it will see at prediction time, or the feature space it
    # learned won't match what it's asked to classify later.
    df["raw_text"] = df["raw_text"].apply(clean_html_text)
    n_before = len(df)
    df = df[df["raw_text"].apply(is_english)]
    n_dropped = n_before - len(df)
    if n_dropped:
        logger.info("language_filter_applied", kept=len(df), dropped=n_dropped)

    if df.empty:
        logger.warning("train_classifier_no_data", note="All labeled postings were filtered out as non-English.")
        return

    result = train_classifier(df[["raw_text", "category_label"]])
    if result is None:
        return  # train_classifier already logged why (not enough examples yet)

    logger.info("train_classifier_complete", n_labeled=len(df),
                sources=df["category_label_source"].value_counts().to_dict())


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--manual-only", action="store_true",
                        help="train on hand labels only (default: hand and LLM labels)")
    args = parser.parse_args()
    run(manual_only=args.manual_only)
