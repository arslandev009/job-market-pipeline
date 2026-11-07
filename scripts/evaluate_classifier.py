"""Honest evaluation of the job-category classifier (M2.5). Writes docs/RESULTS.md.

What it does differently from the CV line inside src/ml/classify.py:
  * the TF-IDF vectorizer sits INSIDE a Pipeline, so it is fitted on the training folds only (no vocabulary leak)
  * near-duplicate postings (TF-IDF cosine >= 0.9) are put into the same group and never split across train/test
  * repeated stratified group k-fold (5 x 5 by default) with mean +/- std, not one lucky split
  * baselines next to the model: most-frequent class and logistic regression on the same features
  * per-class precision/recall/F1 and a confusion matrix, not just accuracy
  * a shuffled-label control: if the score does not fall to chance when the labels are shuffled, something leaks
  * hand-labelled ('manual', gold) rows are reported separately from LLM-labelled ('llm', silver) rows

Run (the docs folder must be mounted so RESULTS.md survives the container):
    docker compose run --rm --no-deps -v "<repo>/docs:/app/docs" ml python -m scripts.evaluate_classifier
"""
from __future__ import annotations

import argparse
import os
import re
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline

from src.ml.features import build_vectorizer

OUT_PATH = Path(__file__).resolve().parents[1] / "docs" / "RESULTS.md"
DUP_THRESHOLD = 0.9


# ---------------------------------------------------------------- core (pure functions, no DB)

def duplicate_groups(texts: np.ndarray, threshold: float = DUP_THRESHOLD) -> tuple[np.ndarray, int]:
    """Group near-identical postings (cosine similarity of TF-IDF vectors >= threshold)."""
    X = TfidfVectorizer(stop_words="english").fit_transform(texts)
    sim = (X @ X.T).toarray()
    parent = list(range(len(texts)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    ii, jj = np.where(np.triu(sim >= threshold, k=1))
    for i, j in zip(ii, jj):
        parent[find(int(i))] = find(int(j))
    roots = np.array([find(i) for i in range(len(texts))])
    _, groups = np.unique(roots, return_inverse=True)
    return groups, len(texts) - len(set(groups.tolist()))


def make_models() -> dict:
    """Every setting is fixed in advance (nothing is tuned on a test fold)."""
    def pipe(clf, max_features: int = 800):
        return lambda: Pipeline([("tfidf", build_vectorizer(max_features)), ("clf", clf())])

    def lr(c: float):
        return lambda: LogisticRegression(C=c, max_iter=2000, class_weight="balanced")

    return {
        "baseline: most frequent class": pipe(lambda: DummyClassifier(strategy="most_frequent")),
        "logistic regression C=1, 800 features": pipe(lr(1.0)),
        "logistic regression C=3, 800 features": pipe(lr(3.0)),
        "logistic regression C=10, 800 features": pipe(lr(10.0)),
        "logistic regression C=3, 3000 features": pipe(lr(3.0), 3000),
        "random forest (current model)": pipe(
            lambda: RandomForestClassifier(n_estimators=200, random_state=42, class_weight="balanced")),
    }


def oof_predict(factory, texts, y, groups, seed: int, n_splits: int) -> np.ndarray:
    pred = np.empty(len(y), dtype=object)
    cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    for train, test in cv.split(texts, y, groups):
        model = factory()
        model.fit(texts[train], y[train])
        pred[test] = model.predict(texts[test])
    return pred


def evaluate(df: pd.DataFrame, repeats: int = 5, shuffle_repeats: int = 3, n_splits: int = 5) -> dict:
    """df columns: text, label, source ('manual' = gold, 'llm' = silver)."""
    texts = df["text"].to_numpy(dtype=object)
    y = df["label"].to_numpy(dtype=object)
    gold = (df["source"] == "manual").to_numpy()
    classes = sorted(set(y.tolist()))
    counts = Counter(y.tolist())
    n_splits = max(2, min(n_splits, min(counts.values())))
    groups, merged = duplicate_groups(texts)
    models = make_models()

    res: dict = {"n": len(y), "n_gold": int(gold.sum()), "n_silver": int((~gold).sum()), "classes": classes,
                 "class_counts": dict(sorted(counts.items(), key=lambda kv: -kv[1])), "n_splits": n_splits,
                 "repeats": repeats, "dup_merged": merged, "models": {}}
    for name, factory in models.items():
        acc, f1, gacc, sacc = [], [], [], []
        pred0 = None
        for rep in range(repeats):
            pred = oof_predict(factory, texts, y, groups, seed=rep, n_splits=n_splits)
            acc.append(accuracy_score(y, pred))
            f1.append(f1_score(y, pred, labels=classes, average="macro", zero_division=0))
            gacc.append(accuracy_score(y[gold], pred[gold]) if gold.any() else float("nan"))
            sacc.append(accuracy_score(y[~gold], pred[~gold]) if (~gold).any() else float("nan"))
            if rep == 0:
                pred0 = pred
        res["models"][name] = {"acc": acc, "macro_f1": f1, "gold_acc": gacc, "silver_acc": sacc, "pred0": pred0}

    best = max((n for n in res["models"] if not n.startswith("baseline")),
               key=lambda n: np.mean(res["models"][n]["macro_f1"]))
    res["best"] = best
    pred0 = res["models"][best]["pred0"]
    res["report"] = classification_report(y, pred0, labels=classes, output_dict=True, zero_division=0)
    res["confusion"] = confusion_matrix(y, pred0, labels=classes).tolist()

    best_factory = models[best]
    shuffled = []
    for k in range(shuffle_repeats):
        ys = np.random.default_rng(1000 + k).permutation(y)
        pred = oof_predict(best_factory, texts, ys, groups, seed=k, n_splits=n_splits)
        shuffled.append(f1_score(ys, pred, labels=classes, average="macro", zero_division=0))
    res["shuffled_macro_f1"] = shuffled
    res["majority_share"] = max(counts.values()) / len(y)
    return res


# ---------------------------------------------------------------- report

def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    adj = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5
    return (centre - adj) / denom, (centre + adj) / denom


def read_llm_check(path: Path) -> tuple[int, int] | None:
    """(agreements, checked) from docs/LLM_LABEL_CHECK.md written by scripts/llm_vs_gold.py, if it exists."""
    if not path.exists():
        return None
    m = re.search(r"agrees with the hand label on \*\*(\d+) of (\d+)\*\*", path.read_text(encoding="utf-8"))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _ms(values) -> str:
    v = np.array(values, dtype=float)
    return "n/a" if np.isnan(v).all() else f"{np.nanmean(v):.3f} ± {np.nanstd(v):.3f}"


def render_markdown(res: dict, today: str, llm_check: tuple[int, int] | None = None) -> str:
    cls = res["classes"]
    if llm_check:
        k, n = llm_check
        lo, hi = wilson(k, n)
        llm_note = (f"On {n} hand-labelled postings the LLM chose the same category as the hand label {k} times "
                    f"({k / n:.0%}, 95% interval {lo:.0%} to {hi:.0%}); see `docs/LLM_LABEL_CHECK.md`.")
    else:
        llm_note = "How often the LLM label is wrong has not been measured yet."
    lines = [
        "# Classifier evaluation (M2)", "",
        f"Generated {today} by `scripts/evaluate_classifier.py`. Every number below comes from that run.", "",
        "## What was evaluated", "",
        f"- **{res['n']} English job postings** in {len(cls)} hand-defined categories "
        f"(`{'`, `'.join(cls)}`).",
        f"- **Labels: {res['n_gold']} by hand (gold), {res['n_silver']} by a local LLM (Qwen3.5-9B, silver).** "
        "Scores measured against the silver labels show how well the classifier reproduces the LLM's labels, "
        "not how well it matches the truth. " + llm_note,
        "- Class counts: " + ", ".join(f"{k} {v}" for k, v in res["class_counts"].items()) + ".", "",
        "## Method", "",
        f"- Repeated stratified group k-fold: {res['n_splits']} folds x {res['repeats']} repeats "
        "(different shuffles). The table shows mean ± std over the repeats; each repeat scores every posting once, "
        "with a model that never saw it.",
        "- The TF-IDF vectorizer is inside the pipeline, so it is fitted on the training folds only.",
        f"- {res['dup_merged']} postings were near-duplicates of another one (cosine >= {DUP_THRESHOLD}); "
        "duplicates are kept in the same fold and never split across train and test.",
        "- No hyperparameter tuning and no separate untouched test set: this is a cross-validation estimate.", "",
        "## Results", "",
        "| model | accuracy | macro-F1 | accuracy on hand-labelled rows (n=%d) | accuracy on LLM-labelled rows |" % res["n_gold"],
        "|---|---|---|---|---|",
    ]
    for name, m in res["models"].items():
        lines.append(f"| {name} | {_ms(m['acc'])} | {_ms(m['macro_f1'])} | {_ms(m['gold_acc'])} | {_ms(m['silver_acc'])} |")
    lines += ["",
              f"The best configuration (**{res['best']}**) was picked by macro-F1 on this same cross-validation, "
              "so its score is slightly optimistic. All settings were fixed in advance; nothing was tuned on a test fold.",
              "",
              f"Accuracy of always guessing the most frequent class: {res['majority_share']:.3f}. "
              "Macro-F1 averages the classes equally, so a model that ignores small classes scores low on it.", "",
              f"## Per class ({res['best']}, first repeat)", "",
              "| class | precision | recall | F1 | postings |", "|---|---|---|---|---|"]
    for c in cls:
        r = res["report"][c]
        lines.append(f"| {c} | {r['precision']:.2f} | {r['recall']:.2f} | {r['f1-score']:.2f} | {int(r['support'])} |")
    lines += ["", "## Confusion matrix (rows = label, columns = prediction, first repeat)", "",
              "| label \\ predicted | " + " | ".join(cls) + " |", "|---|" + "---|" * len(cls)]
    for c, row in zip(cls, res["confusion"]):
        lines.append(f"| {c} | " + " | ".join(str(v) for v in row) + " |")
    lines += ["", "## Leakage control", "",
              f"{res['best']} with the labels **shuffled**: macro-F1 {_ms(res['shuffled_macro_f1'])} "
              f"(the real labels give {_ms(res['models'][res['best']]['macro_f1'])}; "
              f"guessing among {len(cls)} classes gives about {1 / len(cls):.2f}). "
              "A score close to chance after shuffling means the pipeline learns from the labels and does not leak "
              "them through the folds.", "",
              "## Limitations", "",
              "- Small data set (a few hundred postings from one scrape of two job APIs), so differences of a few "
              "points between models are inside the noise (see the ± values).",
              "- Most labels come from an LLM that makes mistakes of its own, for example on borderline roles "
              "such as account managers, product managers and designers.",
              "- The categories were defined by hand for this data; roles that fit none of them end up in `other`.",
              "- Only English postings are used.", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- data + CLI

def load_data() -> pd.DataFrame:
    from sqlalchemy import select

    from src.common.db import get_engine
    from src.common.language import is_english
    from src.common.models import Posting
    from src.common.text_clean import clean_html_text

    q = (select(Posting.id, Posting.raw_text, Posting.category_label, Posting.category_label_source)
         .where(Posting.category_label.is_not(None))
         .where(Posting.category_label_source.in_(["manual", "llm"])))
    raw = pd.read_sql(q, get_engine())
    raw["text"] = raw["raw_text"].fillna("").apply(clean_html_text)
    raw = raw[raw["text"].apply(is_english)]
    return raw.rename(columns={"category_label": "label", "category_label_source": "source"})[
        ["id", "text", "label", "source"]].reset_index(drop=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--no-mount-check", action="store_true", help="tests only")
    a = ap.parse_args()
    if not a.no_mount_check and not os.path.ismount(str(OUT_PATH.parent)):
        print('REFUSED: the docs folder is not mounted, RESULTS.md would be lost with the container.\n'
              'Run with:  -v "<repo path with forward slashes>/docs:/app/docs"')
        return 1
    df = load_data()
    print(f"{len(df)} labelled English postings ({int((df['source'] == 'manual').sum())} hand, "
          f"{int((df['source'] == 'llm').sum())} LLM)")
    if df["label"].nunique() < 2 or len(df) < 50:
        print("Not enough labelled data for a meaningful evaluation.")
        return 1
    res = evaluate(df, repeats=a.repeats)
    md = render_markdown(res, date.today().isoformat(), read_llm_check(OUT_PATH.parent / "LLM_LABEL_CHECK.md"))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(md, encoding="utf-8")
    print(md)
    print(f"\nwritten: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
