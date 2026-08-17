"""
One-off script: determines a sensible k for KMeans clustering by computing
inertia across a range of candidate k values (the "elbow curve" Phase 4 of the
guide calls for). Run this once before Phase 6's first real run, inspect the
saved plot, then hardcode the chosen k into src/ml/main.py's DEFAULT_K.

Deliberately reuses src.ml.features.build_vectorizer() rather than building a
separate TF-IDF setup here — the whole point of an elbow curve is to tell you
what k looks like for the *exact* feature space clustering will actually use;
computing it on a different vectorizer (or un-cleaned / non-English-filtered
text) would make the chosen k meaningless. Applies the same HTML-cleaning and
English-only filtering as src/ml/main.py for that reason.

Run: docker compose run --rm ml python scripts/elbow_curve.py
(requires the ml service's docker-compose volume mount for /app/data, or the
saved plot never reaches your host filesystem)
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")  # no display inside the container
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.cluster import KMeans
from sqlalchemy import select

from src.common.db import get_engine
from src.common.language import is_english
from src.common.logging import configure_logging, get_logger
from src.common.models import Posting
from src.common.text_clean import clean_html_text
from src.ml.features import build_vectorizer

logger = get_logger(__name__)

K_RANGE = range(2, 11)
OUTPUT_DIR = "/app/data/eda"
OUTPUT_PATH = f"{OUTPUT_DIR}/elbow_curve.png"


def main() -> None:
    configure_logging()
    engine = get_engine()
    df = pd.read_sql(select(Posting).order_by(Posting.id), engine, index_col="id")

    if df.empty:
        logger.warning("elbow_curve_no_data", note="Run the scraper first.")
        return

    df["raw_text"] = df["raw_text"].apply(clean_html_text)

    n_before = len(df)
    df = df[df["raw_text"].apply(is_english)]
    n_dropped = n_before - len(df)
    if n_dropped:
        logger.info("language_filter_applied", kept=len(df), dropped=n_dropped)

    if df.empty:
        logger.warning("elbow_curve_no_data", note="All postings filtered out as non-English.")
        return

    vectorizer = build_vectorizer()
    X = vectorizer.fit_transform(df["raw_text"].fillna(""))

    inertias = []
    for k in K_RANGE:
        km = KMeans(n_clusters=k, n_init=10, random_state=42)
        km.fit(X)
        inertias.append(km.inertia_)
        logger.info("elbow_point", k=k, inertia=round(km.inertia_, 1))

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plt.plot(list(K_RANGE), inertias, marker="o")
    plt.xlabel("k (number of clusters)")
    plt.ylabel("Inertia (within-cluster sum of squares)")
    plt.title(f"Elbow curve — {len(df)} job postings (English-only, cleaned)")
    plt.savefig(OUTPUT_PATH)
    logger.info("elbow_curve_saved", path=OUTPUT_PATH, n_postings=len(df))

    print("\nk, inertia, drop-from-previous")
    for i, k in enumerate(K_RANGE):
        drop = "-" if i == 0 else round(inertias[i - 1] - inertias[i], 1)
        print(f"{k}, {round(inertias[i], 1)}, {drop}")


if __name__ == "__main__":
    main()