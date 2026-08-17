"""
PUBLIC portfolio version of the dashboard — read-only, no pipeline controls.

Deployed to Streamlit Community Cloud. Reads from a cloud snapshot database
(synced via scripts/sync_to_cloud.py) instead of your local Postgres, so this
page works permanently regardless of whether your machine is on.

Local dev/full version with pipeline controls: src/dashboard/app.py
"""
from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

st.set_page_config(page_title="Job Market Pipeline — Live Demo", page_icon="💼", layout="wide")

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
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_engine():
    # CLOUD_DATABASE_URL comes from Streamlit Cloud's secrets manager, not a
    # local .env file — see "Secrets" in the app's settings once deployed.
    url = st.secrets["CLOUD_DATABASE_URL"]
    return create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")


def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


# --- header -----------------------------------------------------------

st.title("💼 Job Market Pipeline")
st.caption("Live demo — scrape → LLM extraction → classify/cluster → score → report.")

with st.expander("ℹ️ About this project", expanded=False):
    st.markdown(
        """
        An end-to-end pipeline that scrapes job postings, extracts structured
        fields using a **locally-hosted 9B-parameter LLM** (grammar-constrained
        JSON output via llama.cpp), classifies and clusters them with classical
        ML, and scores each posting's fit against a configurable skill profile
        — combining genuine AI judgment with a deterministic rule-based formula
        as a safety net against LLM inconsistency.

        This page shows a **snapshot of real output** from the pipeline. The
        full system (scraping, live LLM extraction, pipeline controls) runs
        locally — see the [GitHub repo](https://github.com/arslandev009/job-market-pipeline)
        for the complete source and architecture.
        """
    )

tab_raw, tab_extract, tab_results = st.tabs(
    ["📥 Raw Scraped Data", "🔍 Extraction Before/After", "🎯 Final Results"]
)

# --- Tab: Raw Scraped Data ------------------------------------------------

with tab_raw:
    df_raw = run_query(
        "SELECT id, source, url, title, company, scraped_at, raw_text FROM postings ORDER BY scraped_at DESC"
    )

    if df_raw.empty:
        st.info("No data synced yet.")
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("Total rows", len(df_raw))
        m2.metric("Sources", df_raw["source"].nunique())
        m3.metric("Avg text length", f'{int(df_raw["raw_text"].str.len().mean())} chars')

        st.markdown("**Source breakdown**")
        st.bar_chart(df_raw["source"].value_counts())

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
        st.info("No extracted data synced yet.")
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
        st.info("No scored data synced yet.")
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("Total scored", len(df_final))
        m2.metric("Avg fit score", f'{df_final["fit_score"].mean():.2f}')
        m3.metric("Strong matches (≥0.7)", int((df_final["fit_score"] >= 0.7).sum()))

        st.markdown("**Score distribution**")
        score_bins = pd.cut(df_final["fit_score"], bins=10).value_counts().sort_index()
        score_bins.index = score_bins.index.astype(str)
        st.bar_chart(score_bins)

        st.dataframe(
            df_final,
            use_container_width=True,
            column_config={
                "fit_score": st.column_config.ProgressColumn(
                    "Fit Score", min_value=0.0, max_value=1.0, format="%.2f"
                ),
                "url": st.column_config.LinkColumn("URL"),
            },
        )