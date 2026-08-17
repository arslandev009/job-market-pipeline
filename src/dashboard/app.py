"""
job-market-pipeline dashboard — run on the HOST, not in Docker.
See RUN_GUIDE.md for setup and usage.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# --- setup ------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

DB_USER = os.environ.get("POSTGRES_USER", "jmp_user")
DB_PASS = os.environ.get("POSTGRES_PASSWORD", "devpass")
DB_NAME = os.environ.get("POSTGRES_DB", "job_market")
DB_PORT = os.environ.get("POSTGRES_PORT", "5432")
DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@localhost:{DB_PORT}/{DB_NAME}"

st.set_page_config(page_title="Job Market Pipeline", page_icon="💼", layout="wide")

# --- custom styling -------------------------------------------------------

st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; }
    div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 10px;
        padding: 14px 16px;
    }
    .status-pill {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 999px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .status-up { background: rgba(46, 204, 113, 0.15); color: #2ecc71; }
    .status-down { background: rgba(231, 76, 60, 0.15); color: #e74c3c; }
    div[data-testid="stTabs"] button { font-size: 1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_engine():
    from sqlalchemy.pool import NullPool

    return create_engine(DATABASE_URL, poolclass=NullPool, isolation_level="AUTOCOMMIT")


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


def check_llama_health() -> bool:
    import httpx

    try:
        resp = httpx.get("http://localhost:8080/health", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


def stream_command(cmd: list[str], placeholder, env: dict | None = None) -> int:
    process = subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env or os.environ.copy(),
    )
    lines: list[str] = []
    for line in iter(process.stdout.readline, ""):
        lines.append(line.rstrip("\n"))
        placeholder.code("\n".join(lines[-300:]), language="text")
    process.stdout.close()
    return process.wait()


# --- sidebar: pipeline controls -------------------------------------------

with st.sidebar:
    st.title("💼 Pipeline Control")

    llama_up = check_llama_health()
    pill_class = "status-up" if llama_up else "status-down"
    pill_text = "● llama-server: online" if llama_up else "● llama-server: offline"
    st.markdown(f'<span class="status-pill {pill_class}">{pill_text}</span>', unsafe_allow_html=True)
    if not llama_up:
        st.caption("Start it in its own terminal first — see RUN_GUIDE.md.")

    st.divider()

    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_resource.clear()
        st.rerun()

    st.divider()
    st.subheader("Danger Zone")
    confirm_truncate = st.checkbox("I understand this deletes all data")
    if st.button("🗑️ Truncate postings table", disabled=not confirm_truncate, use_container_width=True):
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE TABLE postings CASCADE;"))
        st.success("Truncated.")

    st.divider()
    st.subheader("Run Pipeline")
    max_per_source = st.number_input("SCRAPER_MAX_PER_SOURCE (0=unlimited)", min_value=0, value=25, step=5)
    run_full = st.button("🚀 Run Full Pipeline", type="primary", use_container_width=True)

    st.divider()
    stage = st.selectbox("Run a single stage", ["scraper", "extractor", "ml", "scorer", "sheets-writer"])
    run_single = st.button(f"▶️ Run {stage} only", use_container_width=True)

# --- header -----------------------------------------------------------

st.title("Job Market Pipeline")
st.caption("Scrape → Extract → Classify → Score → Report — end to end, one dashboard.")

log_placeholder = st.empty()

if run_full:
    env = os.environ.copy()
    env["SCRAPER_MAX_PER_SOURCE"] = str(max_per_source)
    with st.spinner("Running full pipeline — this can take several minutes..."):
        exit_code = stream_command(["docker", "compose", "up", "--build"], log_placeholder, env)
    st.success("Pipeline finished.") if exit_code == 0 else st.error(f"Exited with code {exit_code}.")

if run_single:
    with st.spinner(f"Running {stage}..."):
        exit_code = stream_command(["docker", "compose", "run", "--rm", "--build", stage], log_placeholder)
    st.success(f"{stage} finished.") if exit_code == 0 else st.error(f"{stage} exited with code {exit_code}.")

tab_raw, tab_extract, tab_results = st.tabs(["📥 Raw Scraped Data", "🔍 Extraction Before/After", "🎯 Final Results"])

# --- Tab: Raw Scraped Data ------------------------------------------------

with tab_raw:
    df_raw = run_query(
        """
        SELECT id, source, url, title, company, scraped_at, raw_text
        FROM postings WHERE extracted_at IS NULL
        ORDER BY scraped_at DESC
        """
    )

    if df_raw.empty:
        st.info("No un-extracted postings right now.")
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("Total rows", len(df_raw))
        m2.metric("Sources", df_raw["source"].nunique())
        m3.metric("Avg text length", f'{int(df_raw["raw_text"].str.len().mean())} chars')

        chart_col, info_col = st.columns([1, 1])
        with chart_col:
            st.markdown("**Source breakdown**")
            st.bar_chart(df_raw["source"].value_counts())
        with info_col:
            st.markdown("**Column info**")
            info_df = pd.DataFrame(
                {"dtype": df_raw.dtypes.astype(str), "non_null": df_raw.notna().sum(), "nulls": df_raw.isna().sum()}
            )
            st.dataframe(info_df, use_container_width=True)

        with st.expander("Summary statistics (describe())"):
            st.dataframe(df_raw.describe(include="all").T, use_container_width=True)

        st.markdown("**Raw rows**")
        st.dataframe(
            df_raw.drop(columns=["raw_text"]).assign(preview=df_raw["raw_text"].str.slice(0, 120) + "..."),
            use_container_width=True,
        )

# --- Tab: Extraction Before/After ------------------------------------------

with tab_extract:
    df_extracted = run_query(
        """
        SELECT id, title, company, source, extracted_at, seniority, remote_or_onsite,
               salary_min, salary_max, location, required_skills, llm_fit_score, llm_fit_reasoning
        FROM postings WHERE extracted_at IS NOT NULL
        ORDER BY extracted_at DESC
        """
    )

    if df_extracted.empty:
        st.info("No extracted postings yet.")
    else:
        st.markdown(f"**{len(df_extracted)} postings extracted**")
        options = df_extracted.apply(lambda r: f"[{r['id']}] {r['title']} — {r['company']}", axis=1).tolist()
        selected = st.selectbox("Pick a posting to inspect", options)
        selected_id = int(selected.split("]")[0].strip("["))

        raw_row = run_query("SELECT raw_text FROM postings WHERE id = :id", {"id": selected_id})
        extracted_row = df_extracted[df_extracted["id"] == selected_id].iloc[0]

        col_before, col_after = st.columns(2)
        with col_before:
            st.markdown("**BEFORE — raw_text**")
            st.text_area("raw", raw_row.iloc[0]["raw_text"], height=380, label_visibility="collapsed")
        with col_after:
            st.markdown("**AFTER — extracted fields**")
            score = extracted_row["llm_fit_score"] or 0
            st.progress(min(max(score, 0.0), 1.0), text=f"Fit score: {score:.2f}")
            st.json(
                {
                    "seniority": extracted_row["seniority"],
                    "remote_or_onsite": extracted_row["remote_or_onsite"],
                    "salary_min": extracted_row["salary_min"],
                    "salary_max": extracted_row["salary_max"],
                    "location": extracted_row["location"],
                    "required_skills": extracted_row["required_skills"],
                    "llm_fit_reasoning": extracted_row["llm_fit_reasoning"],
                }
            )

        with st.expander("All extracted postings"):
            st.dataframe(df_extracted, use_container_width=True)

# --- Tab: Final Results ----------------------------------------------------

with tab_results:
    df_final = run_query(
        """
        SELECT fit_score, title, company, category_label, seniority, remote_or_onsite,
               location, salary_min, salary_max, required_skills, source, url
        FROM postings WHERE fit_score IS NOT NULL
        ORDER BY fit_score DESC
        """
    )

    if df_final.empty:
        st.info("No scored postings yet.")
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("Total scored", len(df_final))
        m2.metric("Avg fit score", f'{df_final["fit_score"].mean():.2f}')
        m3.metric("Strong matches (≥0.7)", int((df_final["fit_score"] >= 0.7).sum()))

        st.markdown("**Score distribution**")
        score_bins = pd.cut(df_final["fit_score"], bins=10).value_counts().sort_index()
        score_bins.index = score_bins.index.astype(str)  # Altair can't serialize Interval objects directly
        st.bar_chart(score_bins)

        f1, f2, f3 = st.columns(3)
        with f1:
            min_score = st.slider("Minimum fit score", 0.0, 1.0, 0.0, 0.05)
        with f2:
            sources = st.multiselect("Source", df_final["source"].unique().tolist())
        with f3:
            categories = st.multiselect("Category", df_final["category_label"].dropna().unique().tolist())

        filtered = df_final[df_final["fit_score"] >= min_score]
        if sources:
            filtered = filtered[filtered["source"].isin(sources)]
        if categories:
            filtered = filtered[filtered["category_label"].isin(categories)]

        st.markdown(f"**{len(filtered)} of {len(df_final)} postings shown**")
        st.dataframe(
            filtered,
            use_container_width=True,
            column_config={
                "fit_score": st.column_config.ProgressColumn(
                    "Fit Score", min_value=0.0, max_value=1.0, format="%.2f"
                ),
                "url": st.column_config.LinkColumn("URL"),
            },
        )

        csv = filtered.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Download as CSV", csv, "job_results.csv", "text/csv")