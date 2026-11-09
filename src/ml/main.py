"""
Runs the classifier (if a trained model exists) and clustering over all postings,
writing category_label / cluster_id back to the database.

Run: python -m src.ml.main
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import select, update

from src.automation.run_logger import run_stage
from src.common.db import get_engine, session_scope
from src.common.language import is_english
from src.common.logging import configure_logging, get_logger
from src.common.models import Posting
from src.common.text_clean import clean_html_text
from src.ml.classify import load_classifier, predict_categories
from src.ml.cluster import describe_clusters, fit_clusters

logger = get_logger(__name__)

DEFAULT_K = 4  # from elbow curve, data/eda/elbow_curve.png — clear bend at k=4, 200 postings


def run() -> None:
    configure_logging()
    with run_stage("ml") as run_ctx:
        engine = get_engine()
        df = pd.read_sql(select(Posting).order_by(Posting.id), engine, index_col="id")

        if df.empty:
            logger.warning("ml_no_data", note="Run the scraper first.")
            return

        # Strip HTML markup and known scraper boilerplate before anything
        # (TF-IDF, classifier) touches this text — see
        # src/common/text_clean.py for why this matters.
        df["raw_text"] = df["raw_text"].apply(clean_html_text)

        # English-only scope (decision 2026-08-12, docs/PROGRESS.md) — drop
        # non-English postings before feature extraction so they can't form
        # language-only clusters instead of market-segment ones.
        n_before = len(df)
        df = df[df["raw_text"].apply(is_english)]
        n_dropped = n_before - len(df)
        if n_dropped:
            logger.info("language_filter_applied", kept=len(df), dropped=n_dropped)

        if df.empty:
            logger.warning("ml_no_data", note="All postings filtered out as non-English.")
            return

        # Self-heal stale cluster_id values (2026-08-15): before the English
        # filter existed, clustering wrote cluster_id to all 200 rows. After
        # the filter was added, only the ~97 in-scope rows get updated each
        # run — but rows that fall OUT of scope were never cleared, so they
        # kept a leftover cluster_id from that old unfiltered run. Anything
        # downstream that used cluster_id as an "is this in scope" flag (see
        # src/scoring/main.py) would then wrongly treat stale rows as valid.
        # Clearing out-of-scope rows every run makes this correct regardless
        # of history, instead of relying on a one-time manual cleanup.
        in_scope_ids = df.index.tolist()
        with session_scope() as session:
            session.execute(
                update(Posting)
                .where(Posting.id.notin_(in_scope_ids))
                .values(cluster_id=None)
            )

        rows_updated = 0

        # --- Classification (only if we have a trained model) ---
        clf_bundle = load_classifier()
        if clf_bundle:
            clf, vectorizer = clf_bundle
            # Hand ('manual') and LLM ('llm') labels are never overwritten by the model's own predictions:
            # that would erase the silver labels and later feed the model its own output back.
            unlabeled_mask = ~df["category_label_source"].isin(["manual", "llm"])
            to_predict = df[unlabeled_mask]
            if not to_predict.empty:
                predictions = predict_categories(to_predict, clf, vectorizer)
                with session_scope() as session:
                    for posting_id, label in predictions.items():
                        session.execute(
                            update(Posting)
                            .where(Posting.id == posting_id)
                            .values(category_label=label, category_label_source="model")
                        )
                rows_updated += len(predictions)
                logger.info("classification_applied", n=len(predictions))
        else:
            logger.info(
                "classification_skipped",
                note="No trained classifier found. Label examples with "
                "scripts/label_batch.py, then retrain (see docs/PHASE6.md).",
            )

        # --- Clustering (always runs — unsupervised, no labels needed) ---
        cluster_labels, _ = fit_clusters(df, k=DEFAULT_K)
        with session_scope() as session:
            for posting_id, cluster_id in cluster_labels.items():
                session.execute(
                    update(Posting)
                    .where(Posting.id == posting_id)
                    .values(cluster_id=int(cluster_id))
                )
        rows_updated += len(cluster_labels)

        summary = describe_clusters(df, cluster_labels)
        for cid, info in summary.items():
            logger.info("cluster_summary", cluster_id=cid, size=info["size"], top_terms=info["top_terms"])

        run_ctx.rows_processed = rows_updated
        logger.info("ml_complete", rows_updated=rows_updated)


if __name__ == "__main__":
    run()