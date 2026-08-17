# Phase 4 — Exploratory Data Analysis (EDA)

## What this phase is, in plain language

Before you build anything smart on top of your data, look at the data. How
much do you actually have? Is it balanced across sources, or is one source
90% of everything? How long is the text — enough for an LLM to extract useful
fields from, or mostly empty? EDA answers these before you waste LLM calls or
training time on data that isn't ready.

## What we built

- **`src/eda/run_eda.py`** — pulls every posting from Postgres into a pandas
  DataFrame and produces:
  - **Missingness report** — % of nulls per column, printed to terminal.
  - **Source balance chart** — bar chart of postings per source.
  - **Text length distribution** — histogram of raw text length; too many
    very-short postings means Phase 5's LLM extraction won't have much to
    work with.
  - **Elbow curve** — runs KMeans across a range of `k` values and plots
    inertia (a measure of how tight the clusters are) against `k`. The point
    where the curve stops dropping sharply ("the elbow") is a reasonable
    starting guess for how many natural market segments exist in your data —
    this number feeds directly into Phase 6's clustering.

## Key concept: the elbow method

More clusters always reduce inertia (in the extreme, one cluster per data
point has zero inertia) — so you can't just pick the k with the lowest
inertia. The elbow method looks for the point of diminishing returns: where
adding another cluster stops meaningfully tightening the groupings. It's a
heuristic, not a proof — the saved plot is worth actually looking at, not just
trusting the auto-suggested number blindly.

## Key concept: EDA is re-runnable, not a one-time notebook

This is a script, not a Jupyter notebook you ran once and forgot. Every time
new data comes in, re-run it — the plots and summary regenerate fresh. Real
pipelines treat EDA as a repeatable diagnostic step, not a one-off exploration.
