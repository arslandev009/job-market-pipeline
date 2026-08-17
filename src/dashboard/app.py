"""
job-market-pipeline dashboard — run on the HOST, not in Docker.

Why host, not containerized (see chat history): the "Run Pipeline" buttons
below shell out to `docker compose ...` exactly like you do manually in
PowerShell. If this app were itself in a container, giving it that same
power would mean mounting the Docker socket into it (docker-in-docker) —
real complexity and a security footgun for a personal project. Running on
the host means it's just another terminal, with a UI.

Setup (one-time):
    pip install -r requirements-dashboard.txt

Run:
    streamlit run src/dashboard/app.py

You still start llama-server.exe manually in its own terminal first, same
as always — this dashboard's "Run Full Pipeline" button only ever triggers
`docker compose up`, nothing about your model server changes.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# --- setup ------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]  # adjust if you place this file elsewhere
load_dotenv(REPO_ROOT / ".env")

# Same credentials your .env already has for the containers, but talking to
# Postgres via localhost since this script runs on the host, not inside the
# Docker network (where the hostname would be "postgres" instead).
DB_USER = os.environ.get("POSTGRES_USER", "jmp_user")
DB_PASS = os.environ.get("POSTGRES_PASSWORD", "devpass")
DB_NAME = os.environ.get("POSTGRES_DB", "job_market")
DB_PORT = os.environ.get("POSTGRES_PORT", "5432")
DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@localhost:{DB_PORT}/{DB_NAME}"

st.set_page_config(page_title="Job Market Pipeline", layout="wide")


@st.cache_resource
def get_engine():
    # NullPool + AUTOCOMMIT: every query gets a brand-new connection with no
    # open transaction carried over from a previous query. Without this, a
    # cached, pooled connection can serve a stale snapshot from before the
    # pipeline last ran — the classic "data is definitely in Postgres but the
    # dashboard shows 0 rows" bug. Correctness here matters more than the
    # small connection-reuse overhead saves.
    from sqlalchemy.pool import NullPool

    return create_engine(
        DATABASE_URL,
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT",
    )


def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params or {})
    except Exception as exc:
        st.error(
            "Can't reach Postgres. Run `docker compose up -d postgres` in a "
            f"terminal, then refresh this page.\n\nDetails: {exc}"
        )
        st.stop()


def stream_command(cmd: list[str], placeholder) -> int:
    """Run a command, streaming its output live into a Streamlit placeholder."""
    process = subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: list[str] = []
    for line in iter(process.stdout.readline, ""):
        lines.append(line.rstrip("\n"))
        # Cap displayed history so a long run doesn't slow the browser down.
        placeholder.code("\n".join(lines[-300:]), language="text")
    process.stdout.close()
    return process.wait()


# --- header -------------------------------------------------------------

st.title("Job Market Pipeline")

if st.button("🔄 Refresh Data"):
    st.cache_resource.clear()
    st.rerun()

col1, col2 = st.columns(2)
with col1:
    if st.button("Check llama-server health"):
        import httpx

        try:
            resp = httpx.get("http://localhost:8080/health", timeout=3)
            if resp.status_code == 200:
                st.success(f"llama-server is up: {resp.json()}")
            else:
                st.error(f"llama-server responded with status {resp.status_code}")
        except Exception as exc:
            st.error(f"llama-server is NOT reachable — start it first. ({exc})")

with col2:
    st.caption("Model server runs in its own terminal — this dashboard doesn't start it.")

tab_run, tab_raw, tab_extract, tab_results = st.tabs(
    ["Run Pipeline", "Raw Scraped Data", "Extraction Before/After", "Final Results"]
)

# --- Tab 1: Run Pipeline -------------------------------------------------

with tab_run:
    st.subheader("Pipeline Control")

    st.markdown("**Step 1 — Truncate old data (optional, for a clean test run)**")
    confirm_truncate = st.checkbox("I understand this deletes all rows in `postings`")
    if st.button("Truncate postings table", disabled=not confirm_truncate):
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE TABLE postings CASCADE;"))
        st.success("postings table truncated.")

    st.divider()
    st.markdown("**Step 2 — Run the pipeline**")

    max_per_source = st.number_input(
        "SCRAPER_MAX_PER_SOURCE (0 = unlimited)", min_value=0, value=25, step=5
    )

    run_col1, run_col2 = st.columns(2)
    log_placeholder = st.empty()

    with run_col1:
        if st.button("Run Full Pipeline (docker compose up --build)", type="primary"):
            env = os.environ.copy()
            env["SCRAPER_MAX_PER_SOURCE"] = str(max_per_source)
            with st.spinner("Running full pipeline — this can take a while..."):
                cmd = ["docker", "compose", "up", "--build"]
                process = subprocess.Popen(
                    cmd,
                    cwd=REPO_ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=env,
                )
                lines: list[str] = []
                for line in iter(process.stdout.readline, ""):
                    lines.append(line.rstrip("\n"))
                    log_placeholder.code("\n".join(lines[-300:]), language="text")
                process.stdout.close()
                exit_code = process.wait()
            if exit_code == 0:
                st.success("Pipeline finished. Check the other tabs for results.")
            else:
                st.error(f"Pipeline exited with code {exit_code} — see log above.")

    with run_col2:
        stage = st.selectbox(
            "Or run a single stage",
            ["scraper", "extractor", "ml", "scorer", "sheets-writer"],
        )
        service_map = {
            "scraper": "scraper",
            "extractor": "extractor",
            "ml": "ml",
            "scorer": "scorer",
            "sheets-writer": "sheets-writer",
        }
        if st.button(f"Run {stage} only"):
            with st.spinner(f"Running {stage}..."):
                exit_code = stream_command(
                    ["docker", "compose", "run", "--rm", "--build", service_map[stage]],
                    log_placeholder,
                )
            if exit_code == 0:
                st.success(f"{stage} finished.")
            else:
                st.error(f"{stage} exited with code {exit_code}.")

# --- Tab 2: Raw Scraped Data ---------------------------------------------

with tab_raw:
    st.subheader("Raw Scraped Data (not yet extracted)")

    df_raw = run_query(
        """
        SELECT id, source, url, title, company, scraped_at, raw_text
        FROM postings
        WHERE extracted_at IS NULL
        ORDER BY scraped_at DESC
        """
    )

    if df_raw.empty:
        st.info("No un-extracted postings right now — either nothing's been scraped, or extraction already ran on everything.")
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("Total rows", len(df_raw))
        m2.metric("Sources", df_raw["source"].nunique())
        m3.metric("Avg raw_text length (chars)", int(df_raw["raw_text"].str.len().mean()))

        st.markdown("**Source breakdown**")
        st.bar_chart(df_raw["source"].value_counts())

        st.markdown("**Column info (dtypes, non-null counts)**")
        info_df = pd.DataFrame(
            {
                "dtype": df_raw.dtypes.astype(str),
                "non_null": df_raw.notna().sum(),
                "null_count": df_raw.isna().sum(),
            }
        )
        st.dataframe(info_df, use_container_width=True)

        st.markdown("**Numeric/summary stats** (`describe()`)")
        st.dataframe(df_raw.describe(include="all").T, use_container_width=True)

        st.markdown("**Raw rows**")
        st.dataframe(
            df_raw.drop(columns=["raw_text"]).assign(
                raw_text_preview=df_raw["raw_text"].str.slice(0, 120) + "..."
            ),
            use_container_width=True,
        )

# --- Tab 3: Extraction Before/After --------------------------------------

with tab_extract:
    st.subheader("Extraction: Before vs After")

    df_extracted = run_query(
        """
        SELECT id, title, company, source, extracted_at,
               seniority, remote_or_onsite, salary_min, salary_max, location,
               required_skills, llm_fit_score, llm_fit_reasoning
        FROM postings
        WHERE extracted_at IS NOT NULL
        ORDER BY extracted_at DESC
        """
    )

    if df_extracted.empty:
        st.info("No extracted postings yet — run the extractor first.")
    else:
        st.markdown(f"**{len(df_extracted)} postings extracted**")

        options = df_extracted.apply(
            lambda r: f"[{r['id']}] {r['title']} — {r['company']}", axis=1
        ).tolist()
        selected = st.selectbox("Pick a posting to inspect", options)
        selected_id = int(selected.split("]")[0].strip("["))

        raw_row = run_query(
            "SELECT raw_text FROM postings WHERE id = :id", {"id": selected_id}
        )
        extracted_row = df_extracted[df_extracted["id"] == selected_id].iloc[0]

        col_before, col_after = st.columns(2)
        with col_before:
            st.markdown("**BEFORE — raw_text**")
            st.text_area(
                "raw_text", raw_row.iloc[0]["raw_text"], height=400, label_visibility="collapsed"
            )
        with col_after:
            st.markdown("**AFTER — extracted fields**")
            st.json(
                {
                    "seniority": extracted_row["seniority"],
                    "remote_or_onsite": extracted_row["remote_or_onsite"],
                    "salary_min": extracted_row["salary_min"],
                    "salary_max": extracted_row["salary_max"],
                    "location": extracted_row["location"],
                    "required_skills": extracted_row["required_skills"],
                    "llm_fit_score": extracted_row["llm_fit_score"],
                    "llm_fit_reasoning": extracted_row["llm_fit_reasoning"],
                }
            )

        st.divider()
        st.markdown("**All extracted postings**")
        st.dataframe(df_extracted, use_container_width=True)

# --- Tab 4: Final Results ------------------------------------------------

with tab_results:
    st.subheader("Final Scored Results")

    df_final = run_query(
        """
        SELECT fit_score, title, company, category_label, seniority,
               remote_or_onsite, location, salary_min, salary_max,
               required_skills, source, url
        FROM postings
        WHERE fit_score IS NOT NULL
        ORDER BY fit_score DESC
        """
    )

    if df_final.empty:
        st.info("No scored postings yet — run the scorer stage first.")
    else:
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        with filter_col1:
            min_score = st.slider("Minimum fit score", 0.0, 1.0, 0.0, 0.05)
        with filter_col2:
            sources = st.multiselect(
                "Source", df_final["source"].unique().tolist(), default=None
            )
        with filter_col3:
            categories = st.multiselect(
                "Category", df_final["category_label"].dropna().unique().tolist(), default=None
            )

        filtered = df_final[df_final["fit_score"] >= min_score]
        if sources:
            filtered = filtered[filtered["source"].isin(sources)]
        if categories:
            filtered = filtered[filtered["category_label"].isin(categories)]

        st.markdown(f"**{len(filtered)} of {len(df_final)} postings shown**")
        st.dataframe(
            filtered,
            use_container_width=True,
            column_config={"url": st.column_config.LinkColumn("URL")},
        )

        csv = filtered.to_csv(index=False).encode("utf-8")
        st.download_button("Download as CSV", csv, "job_results.csv", "text/csv")