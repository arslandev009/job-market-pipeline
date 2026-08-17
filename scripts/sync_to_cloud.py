"""
Pushes your scored postings from LOCAL Postgres to a free cloud Postgres
(Neon/Supabase), so the public portfolio dashboard always has real data to
show without needing your machine, Docker, or the model server running.

This is a snapshot sync, not a live connection — run it manually (or add to
your pipeline) after any local run you want reflected in the public demo.

Setup (one-time):
    1. Create a free project at neon.tech (or supabase.com)
    2. Add to your local .env:
       CLOUD_DATABASE_URL=postgresql://user:pass@host/dbname?sslmode=require

Run:
    python scripts/sync_to_cloud.py
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

LOCAL_DB_USER = os.environ.get("POSTGRES_USER", "jmp_user")
LOCAL_DB_PASS = os.environ.get("POSTGRES_PASSWORD", "devpass")
LOCAL_DB_NAME = os.environ.get("POSTGRES_DB", "job_market")
LOCAL_DB_PORT = os.environ.get("POSTGRES_PORT", "5432")
LOCAL_DATABASE_URL = f"postgresql+psycopg2://{LOCAL_DB_USER}:{LOCAL_DB_PASS}@localhost:{LOCAL_DB_PORT}/{LOCAL_DB_NAME}"

CLOUD_DATABASE_URL = os.environ.get("CLOUD_DATABASE_URL")

# Only the columns the public dashboard actually needs — no need to ship
# raw_payload, internal run metadata, etc. to a public-facing database.
SYNC_COLUMNS = """
    id, source, url, title, company, raw_text, scraped_at,
    seniority, remote_or_onsite, salary_min, salary_max, location,
    required_skills, extracted_at, llm_fit_score, llm_fit_reasoning,
    category_label, cluster_id, fit_score
"""

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS postings (
    id INTEGER PRIMARY KEY,
    source TEXT,
    url TEXT,
    title TEXT,
    company TEXT,
    raw_text TEXT,
    scraped_at TIMESTAMPTZ,
    seniority TEXT,
    remote_or_onsite TEXT,
    salary_min INTEGER,
    salary_max INTEGER,
    location TEXT,
    required_skills TEXT[],
    extracted_at TIMESTAMPTZ,
    llm_fit_score FLOAT,
    llm_fit_reasoning TEXT,
    category_label TEXT,
    cluster_id INTEGER,
    fit_score FLOAT
);
"""


def main() -> None:
    if not CLOUD_DATABASE_URL:
        raise SystemExit(
            "CLOUD_DATABASE_URL not set in .env — add your Neon/Supabase "
            "connection string first. See this script's docstring."
        )

    local_engine = create_engine(LOCAL_DATABASE_URL)
    cloud_engine = create_engine(CLOUD_DATABASE_URL)

    print("Reading scored postings from local database...")
    with local_engine.connect() as conn:
        df = pd.read_sql(
            text(f"SELECT {SYNC_COLUMNS} FROM postings WHERE fit_score IS NOT NULL"),
            conn,
        )

    if df.empty:
        print("No scored postings found locally — run the pipeline first.")
        return

    print(f"Found {len(df)} scored postings. Pushing to cloud...")

    with cloud_engine.begin() as conn:
        conn.execute(text(CREATE_TABLE_SQL))
        # Wipe and reload — simplest correct approach for a small snapshot
        # table; avoids needing per-row upsert logic for a one-way sync.
        conn.execute(text("TRUNCATE TABLE postings;"))

    df.to_sql("postings", cloud_engine, if_exists="append", index=False, method="multi", chunksize=100)

    print(f"Done. {len(df)} postings now live in the cloud database.")


if __name__ == "__main__":
    main()