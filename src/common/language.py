"""
Language detection for filtering non-English postings out of the ML pipeline.

Decision made 2026-08-12 (see docs/PROGRESS.md): pipeline scope is English-
language postings only. German and Portuguese postings were confirmed present
in the scraped data (source: remoteok, which aggregates from multiple boards)
and were the direct cause of two of four k=4 clusters being language clusters
("sie/und/mit/der" vs. "du/der/die/von") instead of market-segment clusters.

CHANGE 2026-08-15: added a confidence threshold. Plain detect() picks
whichever language scores highest even by a razor-thin margin, which let two
short, tech-loanword-heavy Portuguese postings ("Suporte N1 REMOTO",
"ADVPL Júnior") slip through as "English" — most of their extractable
vocabulary was English tech terms (python, docker, nosql, git, ADVPL) with
only a little genuine Portuguese grammar around them, which is exactly the
kind of text a statistical language guesser gets least confident about.
Requiring the top guess to also clear MIN_CONFIDENCE catches these without
throwing out detect()'s result entirely.

NOTE this is a real precision/recall trade-off, not a strict improvement:
raising the bar will also drop some genuinely-English postings that happen to
score low confidence (unusual formatting, heavy jargon, very short body
text). MIN_CONFIDENCE is deliberately a named constant, not buried in the
function, so it's easy to tune after seeing how the kept/dropped count moves.
"""
from __future__ import annotations

from langdetect import DetectorFactory, LangDetectException, detect_langs

from src.common.logging import get_logger

logger = get_logger(__name__)

# See module docstring — determinism fix (2026-08-13 bug: same table filtered
# to a different row count on every run because langdetect's scorer is
# unseeded by default).
DetectorFactory.seed = 0

# How confident detect_langs() must be in its top guess for us to trust it.
# 1.0 = only accept postings where "en" is essentially the only language
# detected; lower values accept more borderline/mixed-language text. Tune
# this by comparing kept/dropped counts before and after a change — there's
# no universally "correct" value, only a trade-off to observe.
MIN_CONFIDENCE = 0.85


def is_english(text: str | None, min_length: int = 20) -> bool:
    """Returns True if text is confidently detected as English.

    Short text (below min_length chars) is treated as English by default
    rather than rejected — langdetect is unreliable on very short strings,
    and silently dropping an ambiguous short posting is worse than keeping
    a handful of borderline cases; TF-IDF's own stopword/min_df filtering
    already limits how much a few short strays can skew a cluster."""
    if not text or len(text.strip()) < min_length:
        return True
    try:
        langs = detect_langs(text)
        if not langs:
            return True
        top = langs[0]
        return top.lang == "en" and top.prob >= MIN_CONFIDENCE
    except LangDetectException:
        # No detectable linguistic content (pure punctuation/numbers/etc.) —
        # keep it rather than dropping silently on an edge case.
        return True