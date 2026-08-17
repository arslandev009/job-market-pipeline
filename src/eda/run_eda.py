"""
Exploratory Data Analysis over the raw scraped postings.

Purpose: before spending LLM calls and ML training time on this data, understand
its actual shape — how balanced are the sources, how much text is there to work
with, and (via the elbow method) a first estimate of how many natural clusters
the market segments into, which feeds directly into Phase 6's KMeans `k`.

Run: python -m src.eda.run_eda
Outputs: docs/eda_report/*.png + a printed summary, both re-runnable any time
new data comes in (nothing here is hand-edited — it's all regenerated).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: no display in a container
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from src.common.db import get_engine
from src.common.logging import configure_logging, get_logger

logger = get_logger(__name__)
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "docs" / "eda_report"


def load_postings() -> pd.DataFrame:
    engine = get_engine()
    return pd.read_sql("SELECT * FROM postings", engine)


def report_missingness(df: pd.DataFrame) -> pd.Series:
    missing_pct = (df.isna().mean() * 100).round(1).sort_values(ascending=False)
    return missing_pct


def plot_source_balance(df: pd.DataFrame) -> None:
    counts = df["source"].value_counts()
    ax = counts.plot(kind="bar", title="Postings per source", color="#4C72B0")
    ax.set_ylabel("count")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "source_balance.png")
    plt.close()


def plot_text_length_distribution(df: pd.DataFrame) -> None:
    lengths = df["raw_text"].fillna("").str.len()
    ax = lengths.plot(kind="hist", bins=40, title="Raw posting text length (chars)")
    ax.set_xlabel("characters")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "text_length_distribution.png")
    plt.close()


def plot_elbow_curve(df: pd.DataFrame, k_range: range = range(2, 12)) -> int:
    """
    Runs KMeans across a range of k on TF-IDF vectors of the posting text, plots
    inertia vs k (the "elbow"), and returns a suggested k — the point where adding
    another cluster stops meaningfully reducing inertia. This suggested k is a
    starting point for Phase 6, not gospel; eyeball the saved plot too.
    """
    texts = df["raw_text"].fillna("").tolist()
    if len(texts) < max(k_range):
        logger.warning(
            "elbow_skipped_insufficient_data",
            n_postings=len(texts),
            note="Need more postings than max(k_range) to run a meaningful elbow curve.",
        )
        return min(4, max(2, len(texts) // 2 or 2))

    vectorizer = TfidfVectorizer(max_features=500, stop_words="english")
    X = vectorizer.fit_transform(texts)

    inertias = []
    for k in k_range:
        km = KMeans(n_clusters=k, n_init=10, random_state=42)
        km.fit(X)
        inertias.append(km.inertia_)

    plt.plot(list(k_range), inertias, marker="o")
    plt.title("Elbow curve (KMeans inertia vs k)")
    plt.xlabel("k")
    plt.ylabel("inertia")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "elbow_curve.png")
    plt.close()

    # Simple elbow heuristic: largest drop in the rate of decrease.
    diffs = [inertias[i - 1] - inertias[i] for i in range(1, len(inertias))]
    if len(diffs) < 2:
        return list(k_range)[0]
    second_diffs = [diffs[i - 1] - diffs[i] for i in range(1, len(diffs))]
    suggested_idx = second_diffs.index(max(second_diffs)) + 1
    return list(k_range)[suggested_idx]


def run() -> None:
    configure_logging()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = load_postings()
    logger.info("eda_loaded", n_postings=len(df))

    if df.empty:
        logger.warning("eda_no_data", note="Run the scraper first: python -m src.scraper.main")
        return

    missing = report_missingness(df)
    plot_source_balance(df)
    plot_text_length_distribution(df)
    suggested_k = plot_elbow_curve(df)

    print("\n=== EDA SUMMARY ===")
    print(f"Total postings: {len(df)}")
    print(f"Sources: {df['source'].value_counts().to_dict()}")
    print("\nMissingness (%):")
    print(missing.to_string())
    print(f"\nSuggested cluster count (k) for Phase 6: {suggested_k}")
    print(f"\nPlots written to: {OUTPUT_DIR}")


if __name__ == "__main__":
    run()
