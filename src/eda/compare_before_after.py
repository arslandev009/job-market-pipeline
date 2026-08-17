"""
Step 4 of the EDA workflow: prove the cleaning step actually did something,
visually. A cleaning script that isn't compared before/after is just an
assertion — this generates the evidence.

Run: python -m src.eda.compare_before_after
(Run this AFTER src.eda.clean — it reads both raw_text and clean_text from
the same rows, so cleaning must have already populated clean_text.)
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import ftfy
import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import select

from src.common.db import get_engine
from src.common.logging import configure_logging, get_logger
from src.common.models import Posting
from src.eda.diagnose import HTML_TAG_PATTERN, MULTI_WHITESPACE_PATTERN

logger = get_logger(__name__)
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "docs" / "eda_report" / "before_after"


def load() -> pd.DataFrame:
    engine = get_engine()
    return pd.read_sql(select(Posting), engine)


def plot_length_distribution(df: pd.DataFrame) -> None:
    raw_lengths = df["raw_text"].fillna("").str.len()
    clean_lengths = df["clean_text"].fillna("").str.len()

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(raw_lengths, bins=40, alpha=0.6, label="raw_text (before)", color="#C44E52")
    ax.hist(clean_lengths, bins=40, alpha=0.6, label="clean_text (after)", color="#4C72B0")
    ax.set_title("Posting text length: before vs. after cleaning")
    ax.set_xlabel("characters")
    ax.set_ylabel("count")
    ax.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "length_before_after.png")
    plt.close()

    logger.info(
        "length_comparison",
        raw_mean=round(raw_lengths.mean()),
        clean_mean=round(clean_lengths.mean()),
        raw_median=round(raw_lengths.median()),
        clean_median=round(clean_lengths.median()),
    )


def plot_html_contamination_before_after(df: pd.DataFrame) -> None:
    raw_html = df["raw_text"].fillna("").apply(lambda t: bool(HTML_TAG_PATTERN.search(t)))
    clean_html = df["clean_text"].fillna("").apply(lambda t: bool(HTML_TAG_PATTERN.search(t)))

    counts = pd.DataFrame(
        {"before (raw_text)": [raw_html.sum(), len(df) - raw_html.sum()],
         "after (clean_text)": [clean_html.sum(), len(df) - clean_html.sum()]},
        index=["contains HTML", "clean"],
    )

    ax = counts.T.plot(kind="bar", stacked=True, color=["#C44E52", "#55A868"], figsize=(7, 5))
    ax.set_title("HTML contamination: before vs. after cleaning")
    ax.set_ylabel("postings")
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "html_contamination_before_after.png")
    plt.close()

    logger.info(
        "html_comparison",
        raw_contaminated=int(raw_html.sum()),
        clean_contaminated=int(clean_html.sum()),
    )


def plot_encoding_corruption_before_after(df: pd.DataFrame) -> None:
    raw_corrupt = df["raw_text"].fillna("").apply(lambda t: ftfy.fix_text(t) != t)
    clean_corrupt = df["clean_text"].fillna("").apply(lambda t: ftfy.fix_text(t) != t)

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.bar(
        ["before (raw_text)", "after (clean_text)"],
        [raw_corrupt.sum(), clean_corrupt.sum()],
        color=["#C44E52", "#55A868"],
    )
    ax.set_title("Postings with mojibake (encoding corruption)")
    ax.set_ylabel("count")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "encoding_corruption_before_after.png")
    plt.close()

    logger.info(
        "encoding_comparison", raw=int(raw_corrupt.sum()), clean=int(clean_corrupt.sum())
    )


def plot_whitespace_before_after(df: pd.DataFrame) -> None:
    raw_bad = df["raw_text"].fillna("").apply(lambda t: bool(MULTI_WHITESPACE_PATTERN.search(t)))
    clean_bad = df["clean_text"].fillna("").apply(lambda t: bool(MULTI_WHITESPACE_PATTERN.search(t)))

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.bar(
        ["before (raw_text)", "after (clean_text)"],
        [raw_bad.sum(), clean_bad.sum()],
        color=["#C44E52", "#55A868"],
    )
    ax.set_title("Postings with whitespace irregularities")
    ax.set_ylabel("count")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "whitespace_before_after.png")
    plt.close()

    logger.info("whitespace_comparison", raw=int(raw_bad.sum()), clean=int(clean_bad.sum()))


def plot_quality_flag_breakdown(df: pd.DataFrame) -> None:
    if "text_quality_flag" not in df.columns or df["text_quality_flag"].isna().all():
        logger.warning("quality_flag_missing", note="Run src.eda.clean first.")
        return

    counts = df["text_quality_flag"].value_counts()
    ax = counts.plot(kind="bar", color="#4C72B0", title="Postings by quality flag (after cleaning)")
    ax.set_ylabel("count")
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "quality_flag_breakdown.png")
    plt.close()


def run() -> None:
    configure_logging()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = load()
    if df.empty:
        print("No postings found. Run the scraper first.")
        return
    if df["clean_text"].isna().all():
        print("No cleaned data found. Run `python -m src.eda.clean` first.")
        return

    plot_length_distribution(df)
    plot_html_contamination_before_after(df)
    plot_encoding_corruption_before_after(df)
    plot_whitespace_before_after(df)
    plot_quality_flag_breakdown(df)

    near_dupe_count = int(df["is_near_duplicate"].fillna(False).sum())

    print("\n=== BEFORE/AFTER SUMMARY ===")
    print(f"Near-duplicates flagged: {near_dupe_count}")
    print(f"Plots written to: {OUTPUT_DIR}")


if __name__ == "__main__":
    run()