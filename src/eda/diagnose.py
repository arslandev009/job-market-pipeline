"""
Step 2 of the EDA workflow: diagnose specific, named data quality problems and
back each one with a number — not just "run .describe() and eyeball it." Every
check here exists because Step 1 (inspect_raw.py) or outside research (RemoteOK's
own docs) pointed at a real, specific thing to check for.

Run: python -m src.eda.diagnose
Output: printed report + docs/eda_report/diagnostics.md (so it's reviewable
without re-running, and so before/after comparisons in Step 4 have something
concrete to compare against).
"""
from __future__ import annotations

import re
from pathlib import Path

import ftfy
import pandas as pd
from sqlalchemy import select

from src.common.db import get_engine
from src.common.logging import configure_logging
from src.common.models import Posting

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "docs" / "eda_report" / "diagnostics.md"

HTML_TAG_PATTERN = re.compile(r"<[a-zA-Z/][^>]{0,30}>")
MULTI_WHITESPACE_PATTERN = re.compile(r"[ \t]{3,}|\n{3,}")


def load_postings() -> pd.DataFrame:
    engine = get_engine()
    return pd.read_sql(select(Posting), engine)


def check_shape(df: pd.DataFrame) -> dict:
    return {"rows": len(df), "columns": len(df.columns)}


def check_missingness(df: pd.DataFrame) -> pd.Series:
    return (df.isna().mean() * 100).round(1).sort_values(ascending=False)


def check_empty_strings_disguised_as_present(df: pd.DataFrame) -> dict:
    """A column can be 0% missing (not NULL) while still being functionally
    useless — an empty string '' or whitespace-only value passes isna() but
    carries no information. This check catches what missingness% alone hides."""
    result = {}
    for col in ["title", "company", "raw_text"]:
        blank = df[col].fillna("").str.strip().eq("").sum()
        if blank:
            result[col] = int(blank)
    return result


def check_html_contamination(df: pd.DataFrame) -> dict:
    """Counts postings whose raw_text contains HTML markup, broken down by
    source — this is the check that turns "RemoteOK's docs say descriptions
    contain HTML" from a claim into a measured fact about *your* actual data."""
    result = {}
    for source in df["source"].unique():
        subset = df[df["source"] == source]
        contains_html = subset["raw_text"].fillna("").apply(
            lambda t: bool(HTML_TAG_PATTERN.search(t))
        )
        result[source] = {
            "affected": int(contains_html.sum()),
            "total": len(subset),
            "pct": round(100 * contains_html.mean(), 1),
        }
    return result


def check_whitespace_irregularities(df: pd.DataFrame) -> int:
    """Runs of 3+ spaces/tabs or 3+ newlines in a row — common when HTML is
    stripped naively or when a source's template leaves formatting artifacts."""
    return int(
        df["raw_text"].fillna("").apply(lambda t: bool(MULTI_WHITESPACE_PATTERN.search(t))).sum()
    )


def check_encoding_corruption(df: pd.DataFrame) -> dict:
    """Fix for a problem this script originally didn't check for at all — found
    only by actually reading Stage 1's raw samples: text like 'weâ\\x80\\x99ve'
    where 'Live Más' should read 'Live Más'. This is mojibake — text that was
    UTF-8 encoded somewhere upstream (in the source's own data) and decoded as
    Latin-1/Windows-1252 at some point, corrupting every curly quote, apostrophe,
    and accented character. Detected here using ftfy's own heuristics (the same
    library used to fix it in Stage 3) rather than a hand-rolled regex, since
    ftfy's detector is tuned against a much wider range of real-world mojibake
    patterns than a few examples from one dataset would cover."""
    result = {}
    for source in df["source"].unique():
        subset = df[df["source"] == source]
        corrupted = subset["raw_text"].fillna("").apply(
            lambda t: ftfy.fix_text(t) != t
        )
        result[source] = {
            "affected": int(corrupted.sum()),
            "total": len(subset),
            "pct": round(100 * corrupted.mean(), 1),
        }
    return result


def check_duplicate_urls(df: pd.DataFrame) -> int:
    """Should always be 0 — the DB's UNIQUE constraint on url makes this
    structurally impossible. Checked anyway: a diagnostic that assumes its own
    constraints can't fail isn't actually diagnosing anything."""
    return int(df["url"].duplicated().sum())


def check_near_duplicate_postings(df: pd.DataFrame) -> pd.DataFrame:
    """Same normalized title + company appearing under more than one source —
    a real possibility for popular remote roles that get cross-posted. Exact
    string match after case/whitespace normalization; deliberately conservative
    (won't catch reworded titles) to avoid false positives at this stage."""
    normalized = (
        df["title"].fillna("").str.strip().str.lower()
        + "||"
        + df["company"].fillna("").str.strip().str.lower()
    )
    dupe_keys = normalized[normalized.duplicated(keep=False) & (normalized != "||")]
    return df.loc[dupe_keys.index, ["id", "source", "title", "company"]].sort_values("title")


def check_text_length_outliers(df: pd.DataFrame) -> dict:
    """IQR method: flags postings whose raw_text length is a statistical outlier
    relative to the rest of the dataset — either suspiciously short (likely a
    broken/empty scrape) or suspiciously long (possibly duplicated content
    within the field, or a non-job page that slipped through)."""
    lengths = df["raw_text"].fillna("").str.len()
    q1, q3 = lengths.quantile([0.25, 0.75])
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    too_short = df[lengths < max(lower, 0)]
    too_long = df[lengths > upper]

    return {
        "q1": round(q1),
        "q3": round(q3),
        "lower_bound": round(max(lower, 0)),
        "upper_bound": round(upper),
        "too_short_count": len(too_short),
        "too_short_ids": too_short["id"].tolist()[:10],
        "too_long_count": len(too_long),
        "too_long_ids": too_long["id"].tolist()[:10],
    }


def check_schema_consistency_across_sources(df: pd.DataFrame) -> dict:
    """Each source's raw_payload is arbitrary JSON from a third party — there's
    no guarantee the two APIs expose the same fields. Knowing which keys are
    source-specific vs. universal matters later if you ever want to pull an
    extra field (e.g. RemoteOK's salary tags) straight from raw_payload instead
    of waiting on the LLM extractor."""
    result = {}
    for source in df["source"].unique():
        subset = df[df["source"] == source]
        all_keys = set()
        for payload in subset["raw_payload"]:
            if payload:
                all_keys.update(payload.keys())
        result[source] = sorted(all_keys)
    return result


def run() -> dict:
    configure_logging()
    df = load_postings()

    if df.empty:
        print("No postings found. Run the scraper first.")
        return {}

    report = {
        "shape": check_shape(df),
        "missingness_pct": check_missingness(df).to_dict(),
        "blank_but_not_null": check_empty_strings_disguised_as_present(df),
        "html_contamination": check_html_contamination(df),
        "encoding_corruption": check_encoding_corruption(df),
        "whitespace_irregularities": check_whitespace_irregularities(df),
        "duplicate_urls": check_duplicate_urls(df),
        "near_duplicates": check_near_duplicate_postings(df),
        "text_length_outliers": check_text_length_outliers(df),
        "schema_by_source": check_schema_consistency_across_sources(df),
    }

    _print_report(report)
    _write_report(report)
    return report


def _print_report(report: dict) -> None:
    print("\n" + "=" * 70)
    print("DIAGNOSTIC REPORT")
    print("=" * 70)

    print(f"\nShape: {report['shape']['rows']} rows x {report['shape']['columns']} columns")

    print("\n--- Missingness (%) ---")
    for col, pct in report["missingness_pct"].items():
        if pct > 0:
            print(f"  {col}: {pct}%")

    print("\n--- Blank-but-not-NULL values (invisible to missingness%) ---")
    if report["blank_but_not_null"]:
        for col, count in report["blank_but_not_null"].items():
            print(f"  {col}: {count} rows")
    else:
        print("  None found.")

    print("\n--- HTML contamination in raw_text ---")
    for source, stats in report["html_contamination"].items():
        print(f"  {source}: {stats['affected']}/{stats['total']} postings ({stats['pct']}%)")

    print("\n--- Encoding corruption (mojibake) in raw_text ---")
    for source, stats in report["encoding_corruption"].items():
        print(f"  {source}: {stats['affected']}/{stats['total']} postings ({stats['pct']}%)")

    print(f"\n--- Whitespace irregularities: {report['whitespace_irregularities']} postings ---")

    print(f"\n--- Duplicate URLs: {report['duplicate_urls']} (should always be 0) ---")

    near_dupes = report["near_duplicates"]
    print(f"\n--- Near-duplicate postings (same title+company, different source): {len(near_dupes)} ---")
    if not near_dupes.empty:
        print(near_dupes.to_string(index=False))

    outliers = report["text_length_outliers"]
    print(f"\n--- Text length outliers (IQR method) ---")
    print(f"  Normal range: {outliers['lower_bound']}-{outliers['upper_bound']} chars")
    print(f"  Too short: {outliers['too_short_count']} postings (ids: {outliers['too_short_ids']})")
    print(f"  Too long: {outliers['too_long_count']} postings (ids: {outliers['too_long_ids']})")

    print("\n--- raw_payload keys by source ---")
    for source, keys in report["schema_by_source"].items():
        print(f"  {source}: {keys}")


def _write_report(report: dict) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Diagnostic Report (raw, pre-cleaning)\n"]
    lines.append(f"- Rows: {report['shape']['rows']}\n")
    lines.append("## Missingness (%)\n")
    for col, pct in report["missingness_pct"].items():
        if pct > 0:
            lines.append(f"- `{col}`: {pct}%\n")
    lines.append("\n## HTML contamination\n")
    for source, stats in report["html_contamination"].items():
        lines.append(f"- `{source}`: {stats['affected']}/{stats['total']} ({stats['pct']}%)\n")
    lines.append("\n## Encoding corruption (mojibake)\n")
    for source, stats in report["encoding_corruption"].items():
        lines.append(f"- `{source}`: {stats['affected']}/{stats['total']} ({stats['pct']}%)\n")
    lines.append(f"\n## Whitespace irregularities: {report['whitespace_irregularities']} postings\n")
    lines.append(f"\n## Duplicate URLs: {report['duplicate_urls']}\n")
    lines.append(f"\n## Near-duplicates: {len(report['near_duplicates'])}\n")
    outliers = report["text_length_outliers"]
    lines.append(
        f"\n## Text length outliers\n- Normal range: {outliers['lower_bound']}-{outliers['upper_bound']} chars\n"
        f"- Too short: {outliers['too_short_count']}\n- Too long: {outliers['too_long_count']}\n"
    )
    OUTPUT_PATH.write_text("".join(lines), encoding="utf-8")


if __name__ == "__main__":
    run()