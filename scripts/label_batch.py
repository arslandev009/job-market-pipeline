"""
Interactive CLI: shows you a posting, asks for a category label and (optionally)
a 1-5 fit rating, saves both. Run this for ~15-30 minutes to build the seed data
that Phase 6's classifier and Phase 7's v2 learned scorer both depend on — there's
no way around a human doing this once; every real supervised-ML project starts here.

Run: python -m scripts.label_batch --n 30

CHANGE FROM v1: category is now a fixed numbered menu instead of free text.
Free-text input meant typos/casing variants ("admin" vs "Admin" vs
"administrative") would silently fragment into separate classes for the
classifier — a fixed menu removes that risk. The categories below were chosen on 2026-11-04 for the M2 evaluation;
revisit them if a labelling batch shows a class that never occurs.
"""
from __future__ import annotations

import argparse

from sqlalchemy import select

from src.common.db import session_scope
from src.common.language import is_english
from src.common.logging import configure_logging
from src.common.models import Posting
from src.common.text_clean import clean_html_text

CATEGORIES = [
    "software_engineering",
    "data_ai_ml",
    "devops_cloud_security",
    "sales_marketing",
    "customer_support_admin",
    "management_finance_hr",
    "other",
]


def _prompt_category() -> str | None:
    print("Category:")
    for i, cat in enumerate(CATEGORIES, start=1):
        print(f"  {i}) {cat}")
    raw = input("Choose a number (blank to skip): ").strip()
    if not raw:
        return None
    if raw.isdigit() and 1 <= int(raw) <= len(CATEGORIES):
        return CATEGORIES[int(raw) - 1]
    print("Not a valid choice — skipping this posting.")
    return None


def run(n: int) -> None:
    configure_logging()
    with session_scope() as session:
        # Filter to English before slicing to n — matches the exact scope
        # src/ml/main.py trains/predicts on. Without this, postings that will
        # never reach the classifier anyway (non-English, filtered out
        # everywhere else in the pipeline) show up here and waste labeling
        # effort. There's no SQL-level way to apply is_english(), so this
        # pulls all not-yet-labeled postings and filters in Python before
        # capping at n.
        unlabeled = session.scalars(
            select(Posting).where(Posting.category_label_source.is_(None))
        ).all()

        candidates = []
        for posting in unlabeled:
            if is_english(clean_html_text(posting.raw_text)):
                candidates.append(posting)
            if len(candidates) >= n:
                break

        if not candidates:
            print("Nothing left to label — every remaining posting is either already "
                  "labeled or filtered out as non-English.")
            return

        print(f"Labeling {len(candidates)} postings. Ctrl+C any time to stop; progress is saved per item.\n")

        for posting in candidates:
            print("=" * 70)
            print(f"[{posting.id}] {posting.title} @ {posting.company}")
            # Cleaned preview (HTML/boilerplate stripped) — easier to actually
            # read while labeling than raw scraped markup.
            print(clean_html_text(posting.raw_text)[:400])
            print("-" * 70)

            category = _prompt_category()
            if not category:
                continue

            rating_raw = input("Fit rating 1-5 (blank to skip): ").strip()
            rating = int(rating_raw) if rating_raw.isdigit() and 1 <= int(rating_raw) <= 5 else None

            posting.category_label = category
            posting.category_label_source = "manual"
            if rating is not None:
                posting.manual_rating = rating
            saved_id = posting.id
            session.commit()  # saved now: a later Ctrl+C or closed terminal cannot lose this label
            print(f"  saved [{saved_id}] -> {category}" + (f", rating {rating}" if rating is not None else ""))

        print("\nDone. Train the classifier with: docker compose run --rm ml python -m scripts.train_classifier")


def fix(posting_id: int) -> None:
    """Re-label one posting (for a slip made earlier). Saved immediately."""
    configure_logging()
    with session_scope() as session:
        posting = session.get(Posting, posting_id)
        if posting is None:
            print(f"No posting with id {posting_id}.")
            return
        print(f"[{posting.id}] {posting.title} @ {posting.company}")
        print(f"current: category={posting.category_label} source={posting.category_label_source} "
              f"rating={posting.manual_rating}")
        print(clean_html_text(posting.raw_text)[:400])
        print("-" * 70)
        category = _prompt_category()
        if not category:
            print("Unchanged.")
            return
        rating_raw = input("Fit rating 1-5 (blank = keep current, 0 = clear): ").strip()
        posting.category_label = category
        posting.category_label_source = "manual"
        if rating_raw == "0":
            posting.manual_rating = None
        elif rating_raw.isdigit() and 1 <= int(rating_raw) <= 5:
            posting.manual_rating = int(rating_raw)
        print(f"Saved [{posting_id}] -> {category}, rating {posting.manual_rating}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=30, help="How many postings to label this batch")
    parser.add_argument("--fix", type=int, metavar="ID", help="Re-label one posting by id instead of starting a batch")
    args = parser.parse_args()
    if args.fix is not None:
        fix(args.fix)
    else:
        run(args.n)
