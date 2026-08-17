"""
Deterministic fallback for seniority, applied only where the LLM left
seniority as "unknown". After two rounds of prompt tightening, a 3B local
model still missed literal, unambiguous title cues ("Chief Operating
Officer", "Administrative Assistant Entry Level") on the large majority of
postings — a real capability limit, not a wording problem further prompt
engineering was fixing. This never overrides a seniority the LLM already
committed to; it only fills gaps.
"""
from __future__ import annotations

import re

# Order matters: first match wins. More senior signals checked first.
_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(chief|ceo|coo|cto|cfo|vp|vice president|president|founder)\b", re.I), "lead"),
    (re.compile(r"\b(director|head of|principal)\b", re.I), "lead"),
    (re.compile(r"\bsenior\b|\bsr\.?\b", re.I), "senior"),
    (re.compile(r"\bintern(ship)?\b|\btrainee\b", re.I), "intern"),
    (re.compile(r"entry.level|\bjunior\b|\bjr\.?\b|\bgraduate\b|new grad", re.I), "junior"),
    (re.compile(r"mid.level", re.I), "mid"),
]


def infer_seniority_from_title(title: str | None) -> str | None:
    if not title:
        return None
    for pattern, label in _RULES:
        if pattern.search(title):
            return label
    return None