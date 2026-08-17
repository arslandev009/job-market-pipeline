"""
Step 1 of the EDA workflow: look at the actual raw data before doing anything
statistical to it. It's tempting to jump straight to summary tables — but a
missingness percentage can't tell you that RemoteOK's description field is full
of raw HTML; only looking at an actual row does. This script exists purely to
force that look.

Run: python -m src.eda.inspect_raw
Run with more rows: python -m src.eda.inspect_raw --n 5
Run for one source only: python -m src.eda.inspect_raw --source remoteok
"""
from __future__ import annotations

import argparse

import pandas as pd
from sqlalchemy import select

from src.common.db import get_engine
from src.common.logging import configure_logging
from src.common.models import Posting

pd.set_option("display.max_colwidth", None)


def inspect(n: int, source: str | None) -> None:
    engine = get_engine()
    query = select(Posting)
    if source:
        query = query.where(Posting.source == source)

    df = pd.read_sql(query, engine)
    if df.empty:
        print("No postings found. Run the scraper first.")
        return

    sample = df.sample(min(n, len(df)), random_state=42)

    for _, row in sample.iterrows():
        print("=" * 90)
        print(f"id={row['id']}  source={row['source']}")
        print(f"title:   {row['title']!r}")
        print(f"company: {row['company']!r}")
        print(f"url:     {row['url']}")
        print("-" * 90)
        print("raw_text (first 600 chars, exactly as stored):")
        print(repr((row["raw_text"] or "")[:600]))
        print("-" * 90)
        payload = row["raw_payload"] or {}
        print(f"raw_payload keys: {sorted(payload.keys())}")
        print()

    print("=" * 90)
    print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns")
    print(f"Dtypes:\n{df.dtypes}")


if __name__ == "__main__":
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=3)
    parser.add_argument("--source", type=str, default=None)
    args = parser.parse_args()
    inspect(args.n, args.source)