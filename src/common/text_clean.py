"""
Strips HTML markup out of scraped posting text before it reaches any
downstream consumer — TF-IDF vectorization (src/ml/features.py) or the LLM
extraction prompt (src/llm_extraction/extractor.py).

Why this exists: the k=4 clustering run on 2026-08-12 surfaced this
concretely — 3 of 4 clusters had top TF-IDF terms like "li", "br", "strong",
"h2", "ul" (HTML tag names) instead of any actual job content. raw_text in
the database still contains unstripped HTML from the scrape, so TF-IDF was
clustering on markup structure (which postings use <li> bullets vs. <br>
line breaks), not job substance. This utility is the fix.

Deliberately kept as a pure function with no DB/model dependency, so it can
be applied consistently at every read site without needing a schema change
or a re-scrape — call it on df["raw_text"] (or posting_text) right after
loading, before anything else touches the text.
"""
from __future__ import annotations

import re
from html import unescape

from bs4 import BeautifulSoup

_WHITESPACE_RE = re.compile(r"\s+")

# Recurring site chrome / injected boilerplate found across scraped postings
# (surfaced by cluster analysis on 2026-08-12 and 2026-08-13 — see
# docs/PROGRESS.md). The "Please mention the word..." line is a prompt-
# injection honeypot some LinkedIn-sourced postings (relayed via the remoteok
# API) embed to catch AI agents auto-applying; it's harmless to our extractor
# (the GBNF grammar has no path for the model to "obey" it), but it's pure
# noise for TF-IDF and needs to be stripped the same as HTML tags.
#
# NOTE: this pattern deliberately matches from "Please mention the word"
# through to the END of the string (DOTALL, no sentence boundary), not just
# the first sentence. The template is multiple sentences long ("...to show
# you read the job post completely. This helps us find applicants who read
# the whole posting..."), and an earlier version of this regex that stopped
# at the first period left the trailing sentences in place — which is
# exactly why "applicants", "job post", "companies" were still dominating a
# whole cluster in the 2026-08-13 run despite the fix "working." Since this
# template is always trailing/appended boilerplate, never content that
# appears mid-description before genuine text, matching to end-of-string is
# safe and far more robust than guessing where the template's last sentence
# ends.
_BOILERPLATE_PATTERNS = [
    re.compile(r"Please mention the word.*", re.IGNORECASE | re.DOTALL),
    # Tolerates the source-level corruption seen in some remoteok postings
    # (e.g. "Linked--In" instead of "LinkedIn") by allowing a few stray
    # characters between "Linked" and "In" — this does NOT fix the general
    # word-splitting corruption (that's an accepted, documented limitation,
    # not something a regex can reliably undo), it just widens this one
    # known, specific match so it isn't silently defeated by it.
    re.compile(r"See this and similar jobs on Linked.{0,3}In\.?", re.IGNORECASE),
    re.compile(r"Posted \d{1,2}:\d{2}:\d{2} ?[AP]M\.?", re.IGNORECASE),
    # Generic embedded "Careers Application Form" widget (surfaced by the
    # small cluster_id=3 in the 2026-08-13 run — Augustus Gelatery postings
    # at multiple store locations shared this identical template verbatim,
    # which is what made them cluster together on form-field words instead
    # of actual job content). Anchored on the distinctive file-upload phrase
    # at the end so it doesn't over-match into real description text that
    # happens to mention "apply" or "details" elsewhere.
    re.compile(
        r"Fill in your details to apply below.*?Max\.? file size: ?\d+ ?MB\.?\s*Required\.?",
        re.IGNORECASE | re.DOTALL,
    ),
]


def clean_html_text(raw: str | None) -> str:
    """Strip HTML tags/entities, known scraper boilerplate, and collapse
    whitespace. Safe on already-clean text (BeautifulSoup on plain text is a
    no-op other than whitespace normalization) — so it's fine to call this
    defensively even where you're not 100% sure the input has markup in it.

    NOTE: this does NOT fix corrupted/interleaved text (words split mid-token
    by upstream anti-scraping obfuscation in the source data itself) — that's
    an accepted, documented limitation of the remoteok source, not something
    fixable by cleaning. See docs/PROGRESS.md, 2026-08-12."""
    if not raw:
        return ""
    text = BeautifulSoup(raw, "html.parser").get_text(separator=" ")
    text = unescape(text)
    for pattern in _BOILERPLATE_PATTERNS:
        text = pattern.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text