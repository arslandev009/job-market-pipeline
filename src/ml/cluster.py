"""
Unsupervised clustering: groups postings into market segments without needing
any labels at all — complementary to the classifier, not a replacement. Where
the classifier answers "what category is this, using categories I defined,"
clustering answers "what natural groupings exist in this data that I might not
have thought to define" (e.g. it might separate "high-salary remote senior" from
"local contract junior" without ever being told those are the axes that matter).

k defaults to whatever Phase 4's EDA elbow curve suggested; override in
config/profile.yaml if you want to force a specific number of segments.
"""
from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from sklearn.cluster import KMeans

from src.common.logging import get_logger
from src.ml.features import build_vectorizer

logger = get_logger(__name__)

MODEL_DIR = Path(__file__).resolve().parents[2] / "data" / "models"
KMEANS_PATH = MODEL_DIR / "kmeans.joblib"
CLUSTER_VECTORIZER_PATH = MODEL_DIR / "cluster_vectorizer.joblib"


def fit_clusters(df: pd.DataFrame, k: int) -> tuple[pd.Series, KMeans]:
    vectorizer = build_vectorizer()
    X = vectorizer.fit_transform(df["raw_text"].fillna(""))

    k = min(k, max(2, len(df) // 5))  # never ask for more clusters than the data can support
    km = KMeans(n_clusters=k, n_init=10, random_state=42)
    labels = km.fit_predict(X)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(km, KMEANS_PATH)
    joblib.dump(vectorizer, CLUSTER_VECTORIZER_PATH)
    logger.info("clustering_complete", k=k, n_postings=len(df))

    return pd.Series(labels, index=df.index), km


def describe_clusters(df: pd.DataFrame, cluster_labels: pd.Series, top_n_terms: int = 8) -> dict:
    """Human-readable summary: top TF-IDF terms per cluster, for the report/README,
    not for the model itself."""
    vectorizer = build_vectorizer()
    X = vectorizer.fit_transform(df["raw_text"].fillna(""))
    terms = vectorizer.get_feature_names_out()

    summary = {}
    for cluster_id in sorted(cluster_labels.unique()):
        mask = (cluster_labels == cluster_id).values
        if mask.sum() == 0:
            continue
        mean_tfidf = X[mask].mean(axis=0).A1
        top_indices = mean_tfidf.argsort()[::-1][:top_n_terms]
        summary[int(cluster_id)] = {
            "size": int(mask.sum()),
            "top_terms": [terms[i] for i in top_indices],
        }
    return summary
